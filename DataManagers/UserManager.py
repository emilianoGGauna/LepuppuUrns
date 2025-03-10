import os
import pymongo
import re
import zlib
import hashlib
from dotenv import load_dotenv
import json
import random
from DataManagers.MailSender import MailSender
from bson.objectid import ObjectId
import base64

class UserManager():
    def __init__(self):
        """Inicializa la conexión con la base de datos."""
        load_dotenv()
        MONGO_URI = os.getenv("MONGO_URI")
        DATABASE_NAME = os.getenv("DATABASE_NAME")

        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]

        # Definir colección
        self.users_col = self.db["usuarios"]
        
    def get_user(self, email):
        """Recupera un usuario por su correo electrónico."""
        user = self.users_col.find_one({"email": email}, {"_id": 0, "client_name": 1, "email": 1, "access": 1})
        return user

    def get_clients(self):
        """Recupera todos los usuarios con acceso 'cliente'."""
        clients = list(self.users_col.find({"access": "cliente"}, {"_id": 1, "client_name": 1, "email": 1, "phone": 1}))
        return clients
    
    def get_admins(self):
        """Recupera todos los usuarios con acceso 'admin'."""
        admins = list(self.users_col.find({"access": "admin"}, {"_id": 1, "client_name": 1, "email": 1, "phone": 1}))
        return admins
    
    def encrypt_password(self, password):
        """Encripta una contraseña utilizando CRC32."""
        encrypted = zlib.crc32(password.encode("utf-8"))
        return str(encrypted)
    
    def generate_verification_code(self):
        """Genera un código de verificación aleatorio de 6 dígitos."""
        return str(random.randint(100000, 999999))
    
    def create_user(self, user_data):
        """Valida y crea un nuevo usuario en la base de datos."""
        required_fields = ["client_name", "phone", "email", "access"]
        
        # Verificar que todos los campos obligatorios estén presentes
        if not all(field in user_data for field in required_fields):
            return {"error": "Faltan campos obligatorios"}
        
        # Validar acceso
        if user_data["access"] not in ["cliente", "admin"]:
            return {"error": "Tipo de acceso inválido. Debe ser 'cliente' o 'admin'"}
        
        # Validar número de teléfono
        if not re.fullmatch(r"\d{10}", user_data["phone"]):
            return {"error": "Número de teléfono inválido. Debe tener exactamente 10 dígitos"}
        
        # Validar correo electrónico
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", user_data["email"]):
            return {"error": "Formato de correo electrónico inválido"}
        
        # Establecer estado de autenticación como False inicialmente
        user_data["auth"] = False
        
        # Generar client_id como un hash del JSON del usuario
        user_data_json = json.dumps(user_data, sort_keys=True)
        user_data["client_id"] = hashlib.sha256(user_data_json.encode()).hexdigest()
        
        # Insertar usuario en la base de datos sin código de verificación ni contraseña
        result = self.users_col.insert_one(user_data)
        return {"éxito": True, "id_insertado": str(result.inserted_id)}
    
    def add_verification_code(self, email):
        """Genera y agrega un código de verificación para un usuario existente."""
        verification_code = self.generate_verification_code()
        result = self.users_col.update_one({"email": email}, {"$set": {"verification_code": verification_code}})
        MailSender().send_email(email, verification_code)
        if result.matched_count == 0:
            return {"error": "Usuario no encontrado"}
        return {"éxito": True, "mensaje": "Código de verificación agregado correctamente", "código_de_verificación": verification_code}
    
    def verify_code(self, email, code):
        """Verifica si el código de verificación proporcionado coincide con el de la base de datos."""
        user = self.users_col.find_one({"email": email, "verification_code": code})
        return True if user else False
    
    def set_user_password(self, email, password):
        """Actualiza la contraseña de un usuario y marca la autenticación como verdadera."""
        encrypted_password = self.encrypt_password(password)
        result = self.users_col.update_one({"email": email}, {"$set": {"contraseña": encrypted_password, "auth": True}, "$unset": {"verification_code": 1}})
        
        if result.matched_count == 0:
            return {"error": "Usuario no encontrado"}
        return {"éxito": True, "mensaje": "Contraseña actualizada correctamente y usuario autenticado"}
        
    def authenticate_user(self, email, password):
        """Recupera la información completa de un usuario si el correo y la contraseña son correctos."""
        encrypted_password = self.encrypt_password(password)
        user = self.users_col.find_one({"email": email, "contraseña": encrypted_password})
        
        if user:
            user["_id"] = str(user["_id"])  # Convertir ObjectId a string para evitar problemas con JSON
            return user
        else:
            return {"error": "Correo electrónico o contraseña inválidos"}
            
    def delete_client(self, client_id):
        """Elimina un cliente basado en su ID."""
        try:
            result = self.users_col.delete_one({"_id": ObjectId(client_id)})
            if result.deleted_count == 0:
                return {"error": "Cliente no encontrado"}
            return {"éxito": True, "mensaje": "Cliente eliminado correctamente"}
        except Exception as e:
            return {"error": f"Error al eliminar el cliente: {str(e)}"}
