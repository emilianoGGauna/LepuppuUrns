from flask import redirect, session, jsonify
import os
import pymongo
import random
import string
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
from bson.objectid import ObjectId

class CarritoManager:
    def __init__(self):
        """Initialize the connection to the database and ensure 'cart' collection exists."""
        load_dotenv()
        MONGO_URI = os.getenv("MONGO_URI")
        DATABASE_NAME = os.getenv("DATABASE_NAME")

        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]

        # Ensure the 'cart' collection exists
        if "cart" not in self.db.list_collection_names():
            self.db.create_collection("cart")
    def generate_random_id(self, length=10):
        """Generates a random string of uppercase letters and digits."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def set_prod_in_cart(self, user_id, product_id, form_data):
        """
        Inserts a product into the 'cart' collection with a unique identifier.
        """
        unique_id = self.generate_random_id()  # Generate a unique 10-character string
        
        cart_entry = {
            "entry_id": unique_id,  # Unique random identifier
            "client": user_id,
            "model": ObjectId(product_id),  # Ensure product_id is stored as ObjectId
            "forms_lleno": form_data,  # Preserve the original data structure
        }
        self.db.cart.insert_one(cart_entry)

    def get_carrito_for_client(self, client_id):
        """
        Retrieves all products in the 'cart' for a specific client.
        """
        carrito_items = list(self.db.cart.find({"client": client_id}))
        
        for item in carrito_items:
            item["_id"] = str(item["_id"])
            item["model"] = str(item["model"])

        return carrito_items

    def remove_from_cart(self, cart_item_id):
        """
        Removes a product from the 'cart' collection based on its _id.
        """
        try:
            result = self.db.cart.delete_one({"_id": ObjectId(cart_item_id)})
            if result.deleted_count > 0:
                return {"success": True, "message": "Producto eliminado del carrito."}
            else:
                return {"success": False, "error": "Producto no encontrado en el carrito."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_product_details_from_cart(self, client_id):
        """
        Retrieves product details (modelo and img_2) from the 'prods' collection for all items in the cart.
        """
        carrito_items = self.get_carrito_for_client(client_id)
        prods_collection = self.db["prods"]
        imgs_collection = self.db["imgs"]  # Ensure the image data is correctly fetched

        cart_details = []

        for item in carrito_items:
            product_id = ObjectId(item["model"])  # Convert back to ObjectId
            product = prods_collection.find_one({"_id": product_id})

            if product:
                model_name = product.get("modelo", "Modelo no encontrado")
                img_2_hash = product.get("img_hashes", {}).get("img_2", None)

                # Fetch actual image data using img_2 hash
                img_data = None
                if img_2_hash:
                    img_doc = imgs_collection.find_one({"_id": img_2_hash}, {"image_data": 1})
                    if img_doc:
                        img_data = img_doc.get("image_data")

                cart_details.append({
                    "_id": item["_id"],
                    "model": model_name,
                    "img_2": f"data:image/png;base64,{img_data}" if img_data else None,
                    "forms_lleno": item["forms_lleno"]
                })

        return cart_details

    def generate_random_id(self, length=10):
        """Generates a random string of uppercase letters and digits."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    def finalizar_compra(self, client_id):
        """
        Finalizes the purchase by moving cart items to the orders collection, 
        generating an order summary, and returning a WhatsApp message link.
        """
        carrito_items = list(self.db.cart.find({"client": client_id}))
        if not carrito_items:
            return {"success": False, "error": "No hay productos en el carrito."}

        # Obtener el nombre del cliente
        usuario_doc = self.db.usuarios.find_one({"_id": ObjectId(client_id)}, {"client_name": 1})
        usuario = usuario_doc["client_name"] if usuario_doc else "Cliente Desconocido"

        # Contar productos y cantidad total
        total_cantidad = sum(int(item["forms_lleno"].get("Cantidad", 0)) for item in carrito_items)
        total_pedidos = len(carrito_items)

        # Generar detalles del pedido
        time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        orden_id = self.generate_random_id()

        # Crear la orden con todos los productos
        order_data = {
            "orden_id": orden_id,
            "client_id": client_id,
            "timestamp": time_stamp,
            "estado": "Enviado",
            "total_pedidos": total_pedidos,
            "total_urnas": total_cantidad,
            "productos": carrito_items  # Guardamos todos los items del carrito dentro de 'productos'
        }

        # Insertar la orden en la colección 'orders'
        self.db.orders.insert_one(order_data)

        # Eliminar los productos del carrito
        self.db.cart.delete_many({"client": client_id})

        # Crear el mensaje para WhatsApp
        mensaje = (
            f"Hola, soy {usuario}.\n"
            f"Orden ID: {orden_id}\n"
            f"Fecha de compra: {time_stamp}\n"
            f"Cantidad de pedidos: {total_pedidos}\n"
            f"Total de urnas: {total_cantidad}\n"
            f"Estado: Enviado\n"
        )

        # Codificar el mensaje para WhatsApp
        mensaje_codificado = urllib.parse.quote(mensaje)
        whatsapp_link = f"https://api.whatsapp.com/send?phone=3325648862&text={mensaje_codificado}"

        return {"success": True, "whatsapp_link": whatsapp_link}