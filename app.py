from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, jsonify, send_file
from DataManagers.UserManager import UserManager
from DataManagers.ProductManager import ProductManager
from DataManagers.CarritoManager import CarritoManager
from DataManagers.PedidosManager import PedidosManager

import os
import json
from collections import OrderedDict
from dotenv import load_dotenv
from datetime import timedelta
import base64

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave_secreta_por_defecto")  # Establecer una clave secreta para la gestión de sesiones

# Inicializar UserManager
user_manager = UserManager()
product_manager = ProductManager()
carrito_manager = CarritoManager()
pedidos_manager = PedidosManager()

##################################################################################################################################
##################################################################################################################################

@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=2)  # Keep session active for 2 hours


@app.route("/", methods=["GET", "POST"])
def login():
    # Si el usuario ya está autenticado, redirigirlo según su rol
    if "user" in session:
        if session.get("access") == "admin":
            return redirect(url_for("admin_catalog"))  # Redirigir al catálogo de administrador
        else:
            return redirect(url_for("catalog"))  # Redirigir al catálogo de cliente
    session.clear()
    # Eliminar toda la sesión
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        user = user_manager.authenticate_user(email, password)
        
        if "error" not in user:
            session["user"] = user["client_name"]
            session["access"] = user["access"]
            session["user_id"] = user["_id"]
            flash("Inicio de sesión exitoso!", "success")
            
            if user["access"] == "cliente":
                return redirect(url_for("catalog"))
            elif user["access"] == "admin":
                return redirect(url_for("admin_pedidos"))
        else:
            flash("Correo electrónico o contraseña inválidos.", "danger")
            return redirect(url_for("login"))
    
    return render_template("login/login.html")

@app.route("/logout")
def logout():
    # Eliminar toda la sesión
    session.clear()

    # Invalida la cookie de sesión
    response = make_response(redirect(url_for("login")))
    response.set_cookie("session", "", expires=0)  # Elimina la cookie de sesión

    # Asegurar que no haya rastros de la sesión anterior
    session.modified = True

    flash("Cierre de sesión exitoso. ¡Vuelve pronto!", "info")
    return response

##################################################################################################################################
# PÁGINA DE REGISTRO
##################################################################################################################################

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        client_name = request.form.get("client_name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        confirm_email = request.form.get("confirm_email")

        if email != confirm_email:
            flash("Los correos electrónicos no coinciden.", "danger")
            return redirect(url_for("register"))

        # Determinar el tipo de acceso según el usuario logueado
        access_type = "cliente"
        if "user" in session and session.get("access") == "admin":
            access_type = "admin"

        user_data = {
            "client_name": client_name,
            "phone": phone,
            "email": email,
            "access": access_type
        }

        result = user_manager.create_user(user_data)
        if "error" in result:
            flash(result["error"], "danger")
            return redirect(url_for("register"))

        user_manager.add_verification_code(email)
        flash("Usuario registrado con éxito! Por favor, revisa tu correo electrónico para el código de verificación.", "success")
        return redirect(url_for("verify_code", email=email))

    return render_template("register/new_user.html")


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")

        # Verificar si el usuario existe antes de enviar el código
        user = user_manager.get_user(email)
        if user:
            user_manager.add_verification_code(email)  # Envía código de verificación al correo
            flash("Se ha enviado un código de verificación a su correo electrónico.", "info")
            return redirect(url_for("verify_code", email=email))
        else:
            flash("El correo electrónico no está registrado.", "danger")

    return render_template("register/forgot_password.html")


@app.route("/verify_code/<email>", methods=["GET", "POST"])
def verify_code(email):

    if request.method == "POST":
        code = request.form.get("verification_code")
        if user_manager.verify_code(email, code):
            flash("Verificación exitosa!", "success")
            return redirect(url_for("set_password", email=email))
        else:
            flash("Código de verificación inválido. Intenta de nuevo.", "danger")
            return redirect(url_for("verify_code", email=email))
    
    return render_template("register/verify_code.html", email=email)

@app.route("/set_password/<email>", methods=["GET", "POST"])
def set_password(email):

    if request.method == "POST":
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        if password != confirm_password:
            flash("Las contraseñas no coinciden.", "danger")
            return redirect(url_for("set_password", email=email))
        
        result = user_manager.set_user_password(email, password)
        if "error" in result:
            flash(result["error"], "danger")
            return redirect(url_for("set_password", email=email))
        
        flash("Contraseña establecida con éxito! Ahora puedes iniciar sesión.", "success")
        return redirect(url_for("login"))
    
    return render_template("register/set_password.html", email=email)

##################################################################################################################################
# CLIENTE
##################################################################################################################################

@app.route("/catalog")
def catalog():
    if "user" not in session or session.get("access") != "cliente":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    products_with_images = product_manager.get_catalogo()
    return render_template("client/catalog.html", products_with_images=products_with_images)

@app.route("/forms")
def forms():
    """Retrieve and display product details from MongoDB."""
    product_id = request.args.get("product_id")
    session['product_id'] = product_id
    if not product_id:
        return "No product ID provided.", 400

    product_details = product_manager.get_forms(product_id)
    product_details['product_id'] = product_id

    return render_template("client/forms.html", product=product_details)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if "user" not in session:
        return jsonify({"success": False, "error": "Usuario no autenticado"}), 403

    try:
        form_data = request.get_json()  # Capturar el JSON en orden

        # Obtener product_id correctamente desde la sesión
        product_id = session.get("product_id")  
        if not product_id:
            return jsonify({"success": False, "error": "No product_id found in session."}), 400

        user_id = session.get("user_id")  # Obtener el ID del cliente desde la sesión
        if not user_id:
            return jsonify({"success": False, "error": "No user_id found in session."}), 400

        # Insert into MongoDB using CarritoManager
        carrito_manager.set_prod_in_cart(user_id, product_id, form_data)

        # Get updated cart count
        carrito_items = carrito_manager.get_carrito_for_client(user_id)
        cart_count = len(carrito_items)


        return jsonify({
            "success": True,
            "message": "Producto agregado al carrito correctamente.",
            "cart_count": cart_count  # Return updated cart count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
@app.route("/carrito")
def carrito():
    if "user" not in session or session.get("access") != "cliente":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    user_id = session.get("user_id")  # Get user ID from session

    # Retrieve detailed cart items, including model name and img_2 (Base64 image)
    cart_items = carrito_manager.get_product_details_from_cart(user_id)

    return render_template("client/carrito.html", cart_items=cart_items)


@app.route("/remove_from_cart/<cart_item_id>", methods=["POST"])
def remove_from_cart(cart_item_id):
    if "user" not in session or session.get("access") != "cliente":
        return jsonify({"success": False, "error": "Acceso no autorizado."}), 403

    result = carrito_manager.remove_from_cart(cart_item_id)
    return jsonify(result)


@app.route("/finalizar_compra", methods=["POST"])
def finalizar_compra():
    if "user" not in session or session.get("access") != "cliente":
        return jsonify({"success": False, "error": "Acceso no autorizado."}), 403

    user_id = session.get("user_id")

    mensaje_codificado = carrito_manager.finalizar_compra(user_id)
    if isinstance(mensaje_codificado, dict):
        return jsonify(mensaje_codificado)  # If there's an error, return it

    whatsapp_link = f"https://api.whatsapp.com/send?phone=3325648862&text={mensaje_codificado}"
    
    return jsonify({"success": True, "whatsapp_link": whatsapp_link})


@app.route("/pedidos")
def pedidos():
    if "user" not in session or session.get("access") != "cliente":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))
    user_id = session.get("user_id")

    pedidos = pedidos_manager.get_pedidos_for_client(user_id)

    return render_template("client/pedidos.html", pedidos = pedidos)

from bson import ObjectId
from bson.errors import InvalidId

@app.route("/descargar_pedido/<pedido_id>")
def descargar_pedido(pedido_id):
    if "user" not in session or session.get("access") != "cliente":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    # Verificar si el ID es un ObjectId válido
    if not ObjectId.is_valid(pedido_id):
        flash("ID de pedido inválido.", "danger")
        return redirect(url_for("pedidos"))

    try:
        excel_file = pedidos_manager.download_excel_cliente(pedido_id)

        if not excel_file:
            flash("No se pudo generar el archivo.", "danger")
            return redirect(url_for("pedidos"))

        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"pedido_{pedido_id}.xlsx"
        )
    
    except InvalidId:
        flash("ID de pedido inválido.", "danger")
        return redirect(url_for("pedidos"))

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("pedidos"))


##################################################################################################################################
# ADMINISTRADOR
##################################################################################################################################

@app.route("/admin_pedidos")
def admin_pedidos():
    if "user" not in session or session.get("access") != "admin":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    pedidos = pedidos_manager.get_pedidos()  # Obtener todos los pedidos
    return render_template("admin/pedidos.html", pedidos=pedidos)

@app.route("/delete_pedido/<pedido_id>", methods=["POST"])
def delete_pedido(pedido_id):
    if "user" not in session or session.get("access") != "admin":
        return jsonify({"error": "Acceso no autorizado"}), 403

    result = pedidos_manager.delete_pedido(pedido_id)
    return jsonify(result)

@app.route("/toggle_estado_pedido/<pedido_id>", methods=["POST"])
def toggle_estado_pedido(pedido_id):
    if "user" not in session or session.get("access") != "admin":
        return jsonify({"error": "Acceso no autorizado"}), 403

    result = pedidos_manager.toggle_estado_pedido(pedido_id)
    return jsonify(result)
@app.route("/download_excel/<pedido_id>", methods=["GET"])
def download_excel(pedido_id):
    if "user" not in session or session.get("access") != "admin":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    output = pedidos_manager.download_excel(pedido_id)
    if output is None:
        return "Pedido no encontrado", 404

    return send_file(output, download_name=f"pedido_{pedido_id}.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/admin_catalog")
def admin_catalog():
    if "user" not in session or session.get("access") != "admin":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    products_with_images = product_manager.get_catalogo()
    return render_template("admin/catalog.html", products_with_images=products_with_images)
@app.route("/update_sort_order", methods=["POST"])
def update_sort_order():
    if "user" not in session or session.get("access") != "admin":
        return jsonify({"success": False, "error": "Acceso no autorizado"}), 403

    product_id = request.form.get("product_id")
    direction = request.form.get("direction")

    if not product_id or not direction:
        return jsonify({"success": False, "error": "Faltan parámetros"}), 400

    result = product_manager.update_sort_order(product_id, direction)
    return jsonify(result)

@app.route("/add_product", methods=["POST"])
def add_product():
    """Route to add a new product with a model name, multiple images for forms, and a single catalog image."""
    
    # ✅ Check Admin Access
    if "user" not in session or session.get("access") != "admin":
        return jsonify({"success": False, "error": "Acceso no autorizado"}), 403

    # ✅ Get Form Data
    model_name = request.form.get("model_name")
    img_2_files = request.files.getlist("img_2")  # Multiple images for forms
    print(len(img_2_files))
    img_1_file = request.files.get("img_1")  # Single image for catalog

    # ✅ Validate Inputs
    if not model_name or not img_2_files or len(img_2_files) == 0 or not img_1_file:
        return jsonify({"success": False, "error": "Faltan parámetros. Debe incluir el nombre del modelo, al menos una imagen para forms y una imagen para catálogo."}), 400

    try:
        # ✅ Encode Images as Base64
        img_2_base64_list = [base64.b64encode(img.read()).decode("utf-8") for img in img_2_files]  # List of images
        img_1_base64 = base64.b64encode(img_1_file.read()).decode("utf-8")  # Single image

        # ✅ Insert Product using `ProductManager`
        result = product_manager.set_new_product(model_name, img_2_base64_list, img_1_base64)
        
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": f"Error al procesar la imagen: {str(e)}"}), 500

@app.route("/delete_product", methods=["POST"])
def delete_product():
    """Deletes a product and removes associated data if not in use."""
    if "user" not in session or session.get("access") != "admin":
        return jsonify({"success": False, "error": "Acceso no autorizado"}), 403

    product_id = request.form.get("product_id")

    if not product_id:
        return jsonify({"success": False, "error": "Falta el ID del producto"}), 400

    result = product_manager.delete_product(product_id)
    return jsonify(result)


@app.route("/admin_forms")
def admin_forms():
    """Retrieve and display product details from MongoDB."""
    product_id = request.args.get("product_id")
    session['product_id'] = product_id  # Store product ID in session

    if not product_id:
        return "No product ID provided.", 400

    product_details = product_manager.get_forms(product_id)

    # ✅ Ensure `product.forms` is always a dictionary before passing to Jinja2
    if isinstance(product_details.get("forms"), str):
        try:
            product_details["forms"] = json.loads(product_details["forms"])  # Convert JSON string to dictionary
        except json.JSONDecodeError:
            return "Error: Los datos del formulario no son un JSON válido.", 500

    elif not isinstance(product_details.get("forms"), dict):  
        return "Error: El formulario no es un diccionario válido.", 500

    product_details['product_id'] = product_id
    return render_template("admin/forms.html", product=product_details)

@app.route("/edit_forms")
def edit_forms():
    """Render the Edit Forms page."""
    product_id = request.args.get("product_id") or session.get("product_id")
    if not product_id:
        return "No product ID provided.", 400

    product_details = product_manager.get_forms(product_id)
    
    # ✅ Ensure `product.forms` is always a dictionary
    if isinstance(product_details.get("forms"), str):
        try:
            product_details["forms"] = json.loads(product_details["forms"])
        except json.JSONDecodeError:
            return "Error: Los datos del formulario no son un JSON válido.", 500

    elif not isinstance(product_details.get("forms"), dict):  
        return "Error: El formulario no es un diccionario válido.", 500

    product_details['product_id'] = product_id
    return render_template("admin/edit_forms.html", product=product_details)

@app.route("/edit_corte_lazer")
def edit_corte_lazer():
    """Render the Edit Corte Lázer page."""
    product_id = request.args.get("product_id") or session.get("product_id")
    if not product_id:
        return "No product ID provided.", 400

    product_details = product_manager.get_forms(product_id)

    # ✅ Ensure `product.corte_lazer` is always a dictionary
    if isinstance(product_details.get("corte_lazer"), str):
        try:
            product_details["corte_lazer"] = json.loads(product_details["corte_lazer"])
        except json.JSONDecodeError:
            return "Error: Los datos del corte láser no son un JSON válido.", 500

    elif not isinstance(product_details.get("corte_lazer"), dict):  
        return "Error: El corte láser no es un diccionario válido.", 500

    product_details['product_id'] = product_id
    return render_template("admin/edit_corte_lazer.html", product=product_details)


@app.route("/set_forms", methods=["POST"])
def set_forms():
    """Recibe un nuevo formulario en JSON y lo actualiza en la base de datos."""
    try:

        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "No JSON data received"}), 400

        product_id = data.get("product_id")
        new_forms_data = data.get("new_forms_data")

        if not product_id or not new_forms_data:
            return jsonify({"success": False, "error": "Faltan parámetros"}), 400

        if not isinstance(new_forms_data, dict):
            return jsonify({"success": False, "error": "El formulario debe ser un diccionario válido."}), 400

        result = product_manager.set_forms(product_id, new_forms_data)

        return jsonify(result), (200 if result["success"] else 400)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/set_corte_lazer", methods=["POST"])
def set_corte_lazer():
    """Recibe un nuevo JSON de corte láser y lo actualiza en la base de datos."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data received"}), 400

        product_id = data.get("product_id")
        new_corte_lazer_data = data.get("new_corte_lazer_data")

        if not product_id or not new_corte_lazer_data:
            return jsonify({"success": False, "error": "Faltan parámetros"}), 400

        if not isinstance(new_corte_lazer_data, dict):
            return jsonify({"success": False, "error": "El corte láser debe ser un diccionario válido."}), 400

        result = product_manager.set_corte_lazer(product_id, new_corte_lazer_data)
        return jsonify(result), (200 if result["success"] else 400)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route("/admin_usuarios")
def admin_usuarios():
    if "user" not in session or session.get("access") != "admin":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    clientes = user_manager.get_clients()
    admins = user_manager.get_admins()

    return render_template("admin/usuarios.html", clientes=clientes, admins=admins, session_user_id=session.get("user_id"))

@app.route("/delete_client/<client_id>", methods=["POST"])
def delete_client(client_id):
    if "user" not in session or session.get("access") != "admin":
        return jsonify({"error": "Acceso no autorizado"}), 403
    
    # Permitir eliminar clientes sin restricciones
    if client_id in [admin["_id"] for admin in user_manager.get_admins()] and client_id != session["user_id"]:
        return jsonify({"error": "No puedes eliminar a otro administrador."}), 403
    
    result = user_manager.delete_client(client_id)
    return jsonify(result)


@app.route("/admin_dashboard")
def admin_dashboard():
    if "user" not in session or session.get("access") != "admin":
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for("login"))

    grafico_clientes, grafico_pedidos_mes, grafico_productos = pedidos_manager.generar_graficos_pedidos()

    return render_template(
        "admin/dashboard.html",
        grafico_clientes=grafico_clientes,
        grafico_pedidos_mes=grafico_pedidos_mes,
        grafico_productos=grafico_productos
    )



if __name__ == "__main__":
    app.run(debug=True)