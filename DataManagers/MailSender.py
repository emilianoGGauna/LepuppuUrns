import os
import random
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

class MailSender:
    def __init__(self):
        """Inicializa la clase con el correo de origen y carga la API key."""
        load_dotenv()
        self.FROM_EMAIL = os.getenv("SENDER_EMAIL")
        self.SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    
    def send_email(self, to_email, code):
        """Envía un correo con un código de verificación y una breve introducción sobre LeppupyUrns."""
        subject = "Tu Código de Verificación"
        content = (
            f"""
            <h2>Bienvenido a LeppupyUrns</h2>
            <p>Hola,</p>
            <p>Somos LeppupyUrns, una entidad dedicada a proporcionar servicios únicos y personalizados.</p>
            <p>Tu código de verificación es: <strong>{code}</strong></p>
            <p>Por favor, usa este código para continuar con tu proceso de registro.</p>
            <p>Atentamente,</p>
            <p><strong>Equipo de LeppupyUrns</strong></p>
            """
        )
        try:
            message = Mail(
                from_email=self.FROM_EMAIL,
                to_emails=to_email,
                subject=subject,
                html_content=content
            )
            sg = SendGridAPIClient(self.SENDGRID_API_KEY)
            response = sg.send(message)
            
            print("Correo enviado exitosamente!")
            print("Código de verificación:", code)
            print("Status Code:", response.status_code)
        except Exception as e:
            print("Error enviando el correo:", str(e))

