import os
import pymongo
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING
import json
import hashlib
from bson import ObjectId


class ProductManager:
    def __init__(self):
        """Initialize the connection to the database."""
        load_dotenv()
        MONGO_URI = os.getenv("MONGO_URI")
        DATABASE_NAME = os.getenv("DATABASE_NAME")

        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]

        # Define collections
        self.prods_col = self.db["prods"]
        self.forms_col = self.db["forms"]
        self.imgs_col = self.db["imgs"]
        self.corte_lazer_col = self.db["corte_lazer"]

    def get_catalogo(self):
        # Step 1: Fetch sorted product details (sorted from greatest to smallest 'sort_order')
        sorted_products = list(self.prods_col.find(
            {}, {"_id": 1, "modelo": 1, "sort_order": 1, "img_hashes.img_2": 1}  # Ensure "modelo" and "sort_order" are included
        ).sort("sort_order", ASCENDING))  # Sorting in ascending order

        # Step 2: Extract all image hashes
        img_hashes = [product.get("img_hashes", {}).get("img_2") for product in sorted_products if "img_hashes" in product]
        img_hashes = list(filter(None, img_hashes))  # Remove None values

        # Step 3: Fetch all images in a single query
        images_data = {
            img["_id"]: img["image_data"]
            for img in self.imgs_col.find({"_id": {"$in": img_hashes}}, {"_id": 1, "image_data": 1})
        }

        # Step 4: Process and structure the final list
        products_with_images = [
            {
                "id": str(product["_id"]),
                "model": product.get("modelo", "Unknown"),  # Ensure model key exists
                "sort_order": product.get("sort_order", 0),  # Ensure sort_order key exists
                "image": f"data:image/png;base64,{images_data.get(product.get('img_hashes', {}).get('img_2'))}"
                if product.get("img_hashes", {}).get("img_2") in images_data else None
            }
            for product in sorted_products
        ]

        return products_with_images

    def get_product_info(self, product_id):
        """Retrieve only the product information from 'prods'."""
        try:
            product = self.prods_col.find_one({"_id": ObjectId(product_id)})
        except:
            return None  # If product_id is invalid
        return product if product else None

    def get_forms(self, product_id):
        """Retrieve the full product details, including multiple images, forms data, and corte_lazer data."""
        product = self.get_product_info(product_id)
        if not product:
            return {"error": "Product not found"}

        # Get actual forms data from 'forms' collection
        forms_hash = product.get("forms_hash")
        forms_data = self.forms_col.find_one({"_id": forms_hash}, {"_id": 0, "forms_data": 1}) if forms_hash else None

        # Get multiple images from 'imgs' collection
        img_hashes = product.get("img_hashes", {}).get("img_1", [])  # Lista de hashes de imágenes
        images = []
        if img_hashes:
            images = [
                f"data:image/png;base64,{img['image_data']}" 
                for img in self.imgs_col.find({"_id": {"$in": img_hashes}}, {"_id": 0, "image_data": 1})
            ]

        # Get corte_lazer data from 'corte_lazer' collection
        corte_lazer_hash = product.get("corte_lazer_hash")
        corte_lazer_data = self.corte_lazer_col.find_one({"_id": corte_lazer_hash}, {"_id": 0, "corte_lazer_data": 1}) if corte_lazer_hash else None

        response = {
            "model": product.get("modelo", "Unknown"),
            "forms": forms_data["forms_data"] if forms_data else "No forms available",
            "images": images if images else ["https://via.placeholder.com/250"],  # Placeholder si no hay imágenes
            "corte_lazer": corte_lazer_data["corte_lazer_data"] if corte_lazer_data else "No corte_lazer data available"
        }

        return response


    def update_sort_order(self, product_id, direction):
        """Cambia el orden del producto en el catálogo."""
        try:
            product = self.prods_col.find_one({"_id": ObjectId(product_id)})
            if not product:
                return {"success": False, "error": "Producto no encontrado"}

            current_order = product.get("sort_order", 0)

            # Encuentra el producto vecino con el cual intercambiar
            if direction == "up":
                swap_product = self.prods_col.find_one({"sort_order": {"$lt": current_order}}, sort=[("sort_order", DESCENDING)])
            elif direction == "down":
                swap_product = self.prods_col.find_one({"sort_order": {"$gt": current_order}}, sort=[("sort_order", ASCENDING)])
            else:
                return {"success": False, "error": "Dirección inválida"}

            if not swap_product:
                return {"success": False, "error": "No hay productos para intercambiar"}

            swap_order = swap_product.get("sort_order", 0)

            # Intercambia los valores de sort_order
            self.prods_col.update_one({"_id": ObjectId(product_id)}, {"$set": {"sort_order": swap_order}})
            self.prods_col.update_one({"_id": swap_product["_id"]}, {"$set": {"sort_order": current_order}})

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}
        
    def generate_hash(self, data):
        """Genera un hash SHA-256 para el contenido del formulario."""
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def set_forms(self, product_id, new_forms_data):
        """Actualiza el formulario asociado a un producto y maneja correctamente los hashes."""
        try:
            if isinstance(new_forms_data, str):  
                try:
                    new_forms_data = json.loads(new_forms_data)
                except json.JSONDecodeError:
                    return {"success": False, "error": "El formulario no es un JSON válido."}

            if not isinstance(new_forms_data, dict):  
                return {"success": False, "error": "El formulario debe ser un diccionario válido."}

            product = self.prods_col.find_one({"_id": ObjectId(product_id)})
            if not product:
                return {"success": False, "error": "Producto no encontrado"}

            # ✅ Generar nuevo hash
            new_forms_hash = self.generate_hash(new_forms_data)

            # ✅ Evitar reinsertar el mismo hash si ya existe
            existing_form = self.forms_col.find_one({"_id": new_forms_hash})
            if not existing_form:
                self.forms_col.insert_one({"_id": new_forms_hash, "forms_data": new_forms_data})

            # ✅ Verificar si hay un hash anterior y eliminarlo si es diferente al nuevo
            old_forms_hash = product.get("forms_hash")
            if old_forms_hash and old_forms_hash != new_forms_hash:
                if self.forms_col.find_one({"_id": old_forms_hash}):
                    self.forms_col.delete_one({"_id": old_forms_hash})
                else:
                    print(f"DEBUG: forms_hash anterior ({old_forms_hash}) no encontrado, omitiendo eliminación.")

            # ✅ Forzar la actualización en MongoDB
            update_result = self.prods_col.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"forms_hash": new_forms_hash}}
            )

            if update_result.modified_count > 0:
                return {"success": True, "message": "Formulario actualizado correctamente"}
            else:
                print(f"DEBUG: forms_hash ya era el mismo, no hubo cambios.")
                return {"success": True, "message": "El formulario ya estaba actualizado."}

        except Exception as e:
            return {"success": False, "error": f"Error al actualizar el formulario: {str(e)}"}

    def set_corte_lazer(self, product_id, new_corte_lazer_data):
        """Actualiza la información de corte láser y maneja correctamente los hashes."""
        try:
            if isinstance(new_corte_lazer_data, str):  
                try:
                    new_corte_lazer_data = json.loads(new_corte_lazer_data)
                except json.JSONDecodeError:
                    return {"success": False, "error": "El corte láser no es un JSON válido."}

            if not isinstance(new_corte_lazer_data, dict):  
                return {"success": False, "error": "El corte láser debe ser un diccionario válido."}

            product = self.prods_col.find_one({"_id": ObjectId(product_id)})
            if not product:
                return {"success": False, "error": "Producto no encontrado"}

            # ✅ Generar nuevo hash
            new_corte_lazer_hash = self.generate_hash(new_corte_lazer_data)

            # ✅ Evitar reinsertar el mismo hash si ya existe
            existing_corte = self.corte_lazer_col.find_one({"_id": new_corte_lazer_hash})
            if not existing_corte:
                self.corte_lazer_col.insert_one({"_id": new_corte_lazer_hash, "corte_lazer_data": new_corte_lazer_data})

            # ✅ Verificar si hay un hash anterior y eliminarlo si es diferente al nuevo
            old_corte_lazer_hash = product.get("corte_lazer_hash")
            if old_corte_lazer_hash and old_corte_lazer_hash != new_corte_lazer_hash:
                if self.corte_lazer_col.find_one({"_id": old_corte_lazer_hash}):
                    self.corte_lazer_col.delete_one({"_id": old_corte_lazer_hash})
                else:
                    print(f"DEBUG: corte_lazer_hash anterior ({old_corte_lazer_hash}) no encontrado, omitiendo eliminación.")

            # ✅ Forzar la actualización en MongoDB
            update_result = self.prods_col.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"corte_lazer_hash": new_corte_lazer_hash}}
            )

            if update_result.modified_count > 0:
                return {"success": True, "message": "Corte láser actualizado correctamente"}
            else:
                print(f"DEBUG: corte_lazer_hash ya era el mismo, no hubo cambios.")
                return {"success": True, "message": "El corte láser ya estaba actualizado."}

        except Exception as e:
            return {"success": False, "error": f"Error al actualizar el corte láser: {str(e)}"}


    def set_new_product(self, model_name, img_2_base64_list, img_1_base64):
        """Crea un nuevo producto con un nombre de modelo, múltiples imágenes para formularios (img_2) y una única imagen de catálogo (img_1)."""
        try:
            if not model_name or not img_2_base64_list or not img_1_base64:
                return {"success": False, "error": "El nombre del modelo, al menos una imagen para formularios y una imagen de catálogo son obligatorios."}
            
            # ✅ Generar hashes y almacenar `img_2` (Múltiples Imágenes para Formularios)
            img_2_hashes = []
            for img_base64 in img_2_base64_list:
                if img_base64:
                    img_hash = hashlib.sha256(img_base64.encode()).hexdigest()
                    
                    if not self.imgs_col.find_one({"_id": img_hash}):
                        self.imgs_col.insert_one({"_id": img_hash, "image_data": img_base64})
                    
                    img_2_hashes.append(img_hash)
            
            # ✅ Generar hash y almacenar `img_1` (Imagen única de catálogo)
            img_1_hash = hashlib.sha256(img_1_base64.encode()).hexdigest()
            
            if not self.imgs_col.find_one({"_id": img_1_hash}):
                self.imgs_col.insert_one({"_id": img_1_hash, "image_data": img_1_base64})
            
            # ✅ Generar hash para `corte_lazer` y `forms`
            empty_dict_hash = hashlib.sha256(str({}).encode()).hexdigest()
            
            if not self.corte_lazer_col.find_one({"_id": empty_dict_hash}):
                self.corte_lazer_col.insert_one({"_id": empty_dict_hash, "corte_lazer_data": {}})
            
            if not self.forms_col.find_one({"_id": empty_dict_hash}):
                self.forms_col.insert_one({"_id": empty_dict_hash, "forms_data": {}})
            
            # ✅ Insertar nuevo producto en `prods_col`
            new_product = {
                "modelo": model_name,
                "img_hashes": {"img_2": img_1_hash, "img_1": img_2_hashes},
                "forms_hash": empty_dict_hash,
                "corte_lazer_hash": empty_dict_hash,
                "sort_order": self.prods_col.count_documents({}) + 1
            }
            
            result = self.prods_col.insert_one(new_product)
            if result.inserted_id:
                return {"success": True, "message": "Producto creado exitosamente", "product_id": str(result.inserted_id)}
            else:
                return {"success": False, "error": "No se pudo insertar el producto"}
        
        except Exception as e:
            return {"success": False, "error": f"Error al crear el producto: {str(e)}"}

        
    def delete_product(self, product_id):
        """Deletes a product and removes associated images, forms, and corte_lazer data if not used elsewhere."""
        try:
            product = self.prods_col.find_one({"_id": ObjectId(product_id)})
            if not product:
                return {"success": False, "error": "Producto no encontrado"}

            # ✅ Extract associated hashes
            img_1_hash = product.get("img_hashes", {}).get("img_1")
            img_2_hash = product.get("img_hashes", {}).get("img_2")
            forms_hash = product.get("forms_hash")
            corte_lazer_hash = product.get("corte_lazer_hash")

            # ✅ Delete the product from the database
            delete_result = self.prods_col.delete_one({"_id": ObjectId(product_id)})
            if delete_result.deleted_count == 0:
                return {"success": False, "error": "No se pudo eliminar el producto"}

            # ✅ Check if images are used by other products before deleting
            if img_1_hash and self.prods_col.count_documents({"img_hashes.img_1": img_1_hash}) == 0:
                self.imgs_col.delete_one({"_id": img_1_hash})
            if img_2_hash and self.prods_col.count_documents({"img_hashes.img_2": img_2_hash}) == 0:
                self.imgs_col.delete_one({"_id": img_2_hash})

            # ✅ Check if forms and corte_lazer are used elsewhere before deleting
            if forms_hash and self.prods_col.count_documents({"forms_hash": forms_hash}) == 0:
                self.forms_col.delete_one({"_id": forms_hash})

            if corte_lazer_hash and self.prods_col.count_documents({"corte_lazer_hash": corte_lazer_hash}) == 0:
                self.corte_lazer_col.delete_one({"_id": corte_lazer_hash})

            return {"success": True, "message": "Producto eliminado correctamente"}

        except Exception as e:
            return {"success": False, "error": f"Error al eliminar el producto: {str(e)}"}
