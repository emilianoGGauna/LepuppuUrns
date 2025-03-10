import os
import io
import re
import pymongo
import plotly.express as px
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import pandas as pd
from collections import defaultdict
import xlsxwriter
from dotenv import load_dotenv
import numpy as np

class PedidosManager:
    def __init__(self):
        """Inicializa la conexión con la base de datos y la colección 'orders'."""
        load_dotenv()
        MONGO_URI = os.getenv("MONGO_URI")
        DATABASE_NAME = os.getenv("DATABASE_NAME")
        
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]
        
        if "orders" not in self.db.list_collection_names():
            self.db.create_collection("orders")

    def get_pedidos_for_client(self, client_id):
        """
        Obtiene todos los pedidos de un cliente específico, ordenados por timestamp del más reciente al más antiguo.
        Reemplaza los IDs de los productos por sus nombres reales.
        """
        pedidos = list(self.db.orders.find({"client_id": client_id}).sort("timestamp", pymongo.DESCENDING))

        # Obtener un diccionario con los nombres reales de los productos usando el _id como clave
        productos_dict = {str(prod["_id"]): prod["modelo"] for prod in self.db.prods.find({}, {"_id": 1, "modelo": 1})}

        for pedido in pedidos:
            pedido["_id"] = str(pedido["_id"])
            pedido["orden_id"] = str(pedido.get("orden_id", "Desconocido"))
            pedido["timestamp"] = pedido.get("timestamp", "Fecha no disponible")
            pedido["estado"] = pedido.get("estado", "Estado no disponible")
            pedido["total_pedidos"] = pedido.get("total_pedidos", 0)
            pedido["total_urnas"] = pedido.get("total_urnas", 0)

            for producto in pedido.get("productos", []):
                producto["model"] = productos_dict[producto['forms_lleno']["product_id"]]# Asegurar que se usa el ID correcto

        return pedidos

    def get_pedidos(self):
        """
        Obtiene todos los pedidos en la base de datos, ordenados del más reciente al más antiguo.
        Reemplaza los client_id por los nombres reales de los clientes.
        """
        pedidos = list(self.db.orders.find().sort("timestamp", pymongo.DESCENDING))

        # Obtener un diccionario con los nombres de los clientes usando el _id como clave
        usuarios_dict = {str(user["_id"]): user["client_name"] for user in self.db.usuarios.find({}, {"_id": 1, "client_name": 1})}

        for pedido in pedidos:
            pedido["_id"] = str(pedido["_id"])
            pedido["orden_id"] = str(pedido.get("orden_id", "Desconocido"))
            pedido["timestamp"] = pedido.get("timestamp", "Fecha no disponible")
            pedido["estado"] = pedido.get("estado", "Estado no disponible")
            pedido["total_pedidos"] = pedido.get("total_pedidos", 0)
            pedido["total_urnas"] = pedido.get("total_urnas", 0)
            
            # Reemplazar el client_id con el nombre real del cliente
            pedido["client_name"] = usuarios_dict[pedido["client_id"]]

        return pedidos


    def delete_pedido(self, pedido_id):
        """Elimina un pedido basado en su ID."""
        result = self.db.orders.delete_one({"_id": ObjectId(pedido_id)})
        return {"success": result.deleted_count > 0}

    def toggle_estado_pedido(self, pedido_id):
        """Alterna el estado del pedido de forma cíclica: Enviado → En Proceso → Terminado → Enviado."""
        pedido = self.db.orders.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            return {"error": "Pedido no encontrado"}

        estado_actual = pedido["estado"]
        nuevo_estado = {
            "Enviado": "En Proceso",
            "En Proceso": "Terminado",
            "Terminado": "Enviado"
        }.get(estado_actual, "Enviado")

        self.db.orders.update_one({"_id": ObjectId(pedido_id)}, {"$set": {"estado": nuevo_estado}})
        return {"success": True, "nuevo_estado": nuevo_estado}

    def generar_graficos_pedidos(self):
        """
        Genera gráficos con estadísticas de los pedidos y devuelve los datos procesados
        """
        pedidos = list(self.db.orders.find())
        usuarios = {str(user["_id"]): user["client_name"] for user in self.db.usuarios.find({}, {"_id": 1, "client_name": 1})}
        productos = {str(prod["_id"]): prod["modelo"] for prod in self.db.prods.find({}, {"_id": 1, "modelo": 1})}
        
        # Convertir datos de pedidos a DataFrame
        df_pedidos = pd.DataFrame(pedidos)
        
        if df_pedidos.empty:
            return None, None, None
        
        # Reemplazar IDs con nombres en DataFrame
        df_pedidos["client_id"] = df_pedidos["client_id"].map(usuarios)
        
        # Clientes con más pedidos
        clientes_contados = df_pedidos["client_id"].value_counts().reset_index()
        clientes_contados.columns = ["Cliente", "Total Pedidos"]
        fig1 = px.bar(clientes_contados, x="Cliente", y="Total Pedidos", title="Clientes con Más Pedidos", color="Cliente")
        
        # Pedidos del último mes
        fecha_limite = datetime.now() - timedelta(days=30)
        df_pedidos["timestamp"] = pd.to_datetime(df_pedidos["timestamp"], errors='coerce')
        df_ultimo_mes = df_pedidos[df_pedidos["timestamp"] >= fecha_limite]
        pedidos_por_fecha = df_ultimo_mes.groupby(df_ultimo_mes["timestamp"].dt.date).size().reset_index(name="Cantidad")
        fig2 = px.line(pedidos_por_fecha, x="timestamp", y="Cantidad", title="Pedidos en el Último Mes", markers=True)
        
        # Producto más vendido
        productos_vendidos = []
        for pedido in pedidos:
            for producto in pedido.get("productos", []):
                productos_vendidos.append(str(producto.get("model")))
        
        df_productos = pd.DataFrame(productos_vendidos, columns=["Producto"])
        df_productos["Producto"] = df_productos["Producto"].map(productos)
        productos_contados = df_productos["Producto"].value_counts().reset_index()
        productos_contados.columns = ["Producto", "Cantidad Vendida"]
        fig3 = px.bar(productos_contados, x="Producto", y="Cantidad Vendida", title="Productos Más Vendidos", color="Producto")
        
        return fig1.to_html(full_html=False), fig2.to_html(full_html=False), fig3.to_html(full_html=False)

    def get_pedidos_por_id(self, pedido_id):
        """
        Obtiene un pedido específico por su ID y reemplaza el client_id por el nombre real del cliente.
        """
        pedido = self.db.orders.find_one({"_id": ObjectId(pedido_id)})

        if not pedido:
            return None  # Retorna None si el pedido no existe

        pedido["_id"] = str(pedido["_id"])
        pedido["orden_id"] = str(pedido.get("orden_id", "Desconocido"))
        pedido["timestamp"] = pedido.get("timestamp", "Fecha no disponible")
        pedido["estado"] = pedido.get("estado", "Estado no disponible")
        pedido["total_pedidos"] = pedido.get("total_pedidos", 0)
        pedido["total_urnas"] = pedido.get("total_urnas", 0)

        # Obtener el nombre del cliente desde la colección usuarios
        usuario = self.db.usuarios.find_one({"_id": ObjectId(pedido["client_id"])}, {"client_name": 1})
        pedido["client_name"] = usuario["client_name"] if usuario else "Cliente Desconocido"

        return pedido

    def generate_pedido_dataframes(self, pedido_id):
        """Genera los DataFrames del pedido, productos y cortes láser."""
        pedido = self.get_pedidos_por_id(pedido_id)

        if not pedido:
            return None, None, None  # Si no existe el pedido, devuelve None en todos los DataFrames

        # Crear DataFrame con información general del pedido
        data_pedido = {
            "Orden ID": [pedido.get("orden_id", "Desconocido")],
            "Cliente": [pedido.get("client_name", "Cliente Desconocido")],
            "Fecha": [pedido.get("timestamp", "Fecha no disponible")],
            "Estado": [pedido.get("estado", "Estado no disponible")],
            "Total Pedidos": [pedido.get("total_pedidos", 0)],
            "Total Urnas": [pedido.get("total_urnas", 0)]
        }
        df_pedido = pd.DataFrame(data_pedido)

        # Obtener diccionario de modelos de la colección 'prods'
        productos_dict = {
            str(prod["_id"]): prod for prod in self.db.prods.find({}, {"_id": 1, "modelo": 1, "corte_lazer_hash": 1})
        }

        # Obtener todas las claves únicas de "forms_lleno" en los productos
        all_keys = set()
        for producto in pedido.get("productos", []):
            all_keys.update(producto.get("forms_lleno", {}).keys())

        # Definir el mapeo de nombres de columnas
        column_mapping = {
            "¿quieres_el_logo_de_tu_empresa?": "logo_grabado",
            "tipo-urna": "tipo-madera"
        }

        # Definir regex para excluir columnas en la tabla "Cortes Láser"
        excluded_columns_regex = re.compile(r"(color|colores|base|bases)", re.IGNORECASE)

        # Crear lista de productos con información completa del formulario
        productos = []
        cortes_laser_dict = defaultdict(lambda: defaultdict(int))  # Para mergear filas duplicadas

        for producto in pedido.get("productos", []):
            product_id = producto.get("forms_lleno", {}).get("product_id")
            producto_info = {
                "Modelo": productos_dict.get(product_id, {}).get("modelo", "Modelo Desconocido"),
            }

            # Agregar todas las claves de forms_lleno con mapeo, excluyendo "product_id"
            for key in all_keys:
                if key != "product_id":  # Excluir la columna "product_id"
                    mapped_key = column_mapping.get(key, key)  # Aplicar mapeo si existe
                    producto_info[mapped_key] = producto.get("forms_lleno", {}).get(key, '-')

            productos.append(producto_info)

            # Obtener el corte láser correspondiente al producto
            corte_lazer_hash = productos_dict.get(product_id, {}).get("corte_lazer_hash")
            corte_entry = {}

            if corte_lazer_hash:
                corte_info = self.db.corte_lazer.find_one({"_id": corte_lazer_hash})
                if corte_info:
                    corte_lazer_data = corte_info.get("corte_lazer_data", {})
                    # Filtrar claves de corte_lazer eliminando las que contienen "color" o "base"
                    corte_lazer_filtered = {
                        k: v for k, v in corte_lazer_data.items() if not excluded_columns_regex.search(k)
                    }

                    # Fusionar datos del form_llenado con corte_lazer solo para las claves permitidas
                    for key in corte_lazer_filtered.keys():
                        if key in producto.get("forms_lleno", {}):
                            corte_entry[key] = producto["forms_lleno"][key]  # Priorizar form_llenado
                        else:
                            corte_entry[key] = corte_lazer_filtered[key]  # Si no está en form_llenado, tomar el original

            # Incluir siempre la Figura si está en forms_lleno
            corte_entry["Figura"] = producto.get("forms_lleno", {}).get("Figura", '-')

            # Añadir cantidad desde el formulario si existe
            cantidad = int(producto.get("forms_lleno", {}).get("Cantidad", 0))
            corte_entry["Cantidad"] = cantidad

            # Crear clave única basada en los valores del corte_lazer sin incluir la cantidad
            corte_key = tuple((k, v) for k, v in corte_entry.items() if k != "Cantidad")

            # Merge de filas duplicadas en Corte Láser sumando las cantidades
            if corte_key in cortes_laser_dict:
                cortes_laser_dict[corte_key]["Cantidad"] += cantidad
            else:
                cortes_laser_dict[corte_key] = corte_entry

        # Convertir cortes_laser_dict en lista de diccionarios
        cortes_laser = list(cortes_laser_dict.values())

        df_productos = pd.DataFrame(productos)
        df_cortes_laser = pd.DataFrame(cortes_laser) if cortes_laser else pd.DataFrame()

        return df_pedido, df_productos, df_cortes_laser

    def download_excel(self, pedido_id):
        """Toma los DataFrames generados y los exporta a un archivo Excel en una sola hoja con formato elegante y colores diferenciados."""
        df_pedido, df_productos, df_cortes_laser = self.generate_pedido_dataframes(pedido_id)

        if df_pedido is None:
            return None  # Si no se generaron DataFrames, retornar None

        # Crear un buffer en memoria
        output = io.BytesIO()
        
        # Crear un archivo Excel con XlsxWriter
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            workbook = writer.book
            worksheet = workbook.add_worksheet("Resumen Pedido")

            # Definir formatos de títulos con diferentes colores por tabla
            title_formats = [
                workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#2F5597', 'font_color': 'white'}),
                workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#009688', 'font_color': 'white'}),
                workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#795548', 'font_color': 'white'})
            ]

            # Definir formatos de encabezados con colores diferenciados
            header_formats = [
                workbook.add_format({'bold': True, 'font_size': 12, 'bg_color': '#D9E1F2', 'align': 'center', 'border': 1}),
                workbook.add_format({'bold': True, 'font_size': 12, 'bg_color': '#B2DFDB', 'align': 'center', 'border': 1}),
                workbook.add_format({'bold': True, 'font_size': 12, 'bg_color': '#D7CCC8', 'align': 'center', 'border': 1})
            ]

            # Formato para celdas de datos
            cell_format = workbook.add_format({'font_size': 11, 'border': 1})
            cell_center_format = workbook.add_format({'font_size': 11, 'border': 1, 'align': 'center'})

            row = 0  # Controla la fila donde se escribe en el Excel

            # Función para escribir DataFrames en el Excel con formato
            def write_dataframe(title, df, start_row, title_format, header_format):
                """Escribe un DataFrame en el archivo con formato y devuelve la siguiente fila disponible."""
                nonlocal worksheet
                if df.empty:
                    return start_row  # Si está vacío, no escribirlo

                # Reemplazar NaN, None, Inf, -Inf con ""
                df = df.replace([np.nan, None, np.inf, -np.inf], "")

                # Escribir título fusionado con color específico
                col_range = len(df.columns) - 1
                worksheet.merge_range(start_row, 0, start_row, col_range, title, title_format)
                start_row += 1

                # Escribir encabezados con formato diferenciado
                for col_num, column_name in enumerate(df.columns):
                    worksheet.write(start_row, col_num, column_name, header_format)
                start_row += 1

                # Escribir datos con formato
                for i, row_data in df.iterrows():
                    for col_num, value in enumerate(row_data):
                        if isinstance(value, (int, float)) and not pd.isna(value):  # Alinear números al centro
                            worksheet.write(start_row, col_num, value, cell_center_format)
                        else:
                            worksheet.write(start_row, col_num, str(value), cell_format)
                    start_row += 1

                # Ajustar automáticamente el ancho de las columnas basado en la celda más larga
                for col_num, column_name in enumerate(df.columns):
                    max_length = max(df[column_name].astype(str).apply(len).max(), len(column_name))
                    worksheet.set_column(col_num, col_num, max_length + 2)

                return start_row + 2  # Dejar espacio entre tablas

            # Escribir cada DataFrame en la hoja con colores diferenciados
            row = write_dataframe("Información del Pedido", df_pedido, row, title_formats[0], header_formats[0])
            row = write_dataframe("Lista de Productos", df_productos, row, title_formats[1], header_formats[1])
            row = write_dataframe("Detalles de Corte Láser", df_cortes_laser, row, title_formats[2], header_formats[2])

        output.seek(0)
        return output

    def generate_pedido_dataframes_cliente(self, pedido_id):
        """Genera los DataFrames del pedido y productos, sin incluir cortes láser."""
        pedido = self.get_pedidos_por_id(pedido_id)

        if not pedido:
            return None, None  # Si no existe el pedido, devuelve None en los DataFrames

        # Crear DataFrame con información general del pedido
        data_pedido = {
            "Orden ID": [pedido.get("orden_id", "Desconocido")],
            "Cliente": [pedido.get("client_name", "Cliente Desconocido")],
            "Fecha": [pedido.get("timestamp", "Fecha no disponible")],
            "Estado": [pedido.get("estado", "Estado no disponible")],
            "Total Pedidos": [pedido.get("total_pedidos", 0)],
            "Total Urnas": [pedido.get("total_urnas", 0)]
        }
        df_pedido = pd.DataFrame(data_pedido)

        # Obtener diccionario de modelos de la colección 'prods'
        productos_dict = {
            str(prod["_id"]): prod for prod in self.db.prods.find({}, {"_id": 1, "modelo": 1})
        }

        # Obtener todas las claves únicas de "forms_lleno" en los productos
        all_keys = set()
        for producto in pedido.get("productos", []):
            all_keys.update(producto.get("forms_lleno", {}).keys())

        # Definir el mapeo de nombres de columnas
        column_mapping = {
            "¿quieres_el_logo_de_tu_empresa?": "logo_grabado",
            "tipo-urna": "tipo-madera"
        }

        # Crear lista de productos con información completa del formulario
        productos = []

        for producto in pedido.get("productos", []):
            product_id = producto.get("forms_lleno", {}).get("product_id")
            producto_info = {
                "Modelo": productos_dict.get(product_id, {}).get("modelo", "Modelo Desconocido"),
            }

            # Agregar todas las claves de forms_lleno con mapeo, excluyendo "product_id"
            for key in all_keys:
                if key != "product_id":  # Excluir la columna "product_id"
                    mapped_key = column_mapping.get(key, key)  # Aplicar mapeo si existe
                    producto_info[mapped_key] = producto.get("forms_lleno", {}).get(key, '-')

            productos.append(producto_info)

        df_productos = pd.DataFrame(productos)

        return df_pedido, df_productos
    def download_excel_cliente(self, pedido_id):
        """Toma los DataFrames generados y los exporta a un archivo Excel en una sola hoja con formato elegante y colores diferenciados."""
        df_pedido, df_productos = self.generate_pedido_dataframes_cliente(pedido_id)

        if df_pedido is None:
            return None  # Si no se generaron DataFrames, retornar None

        # Crear un buffer en memoria
        output = io.BytesIO()
        
        # Crear un archivo Excel con XlsxWriter
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            workbook = writer.book
            worksheet = workbook.add_worksheet("Resumen Pedido")

            # Definir formatos de títulos con diferentes colores por tabla
            title_formats = [
                workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#2F5597', 'font_color': 'white'}),
                workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#009688', 'font_color': 'white'}),
                workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#795548', 'font_color': 'white'})
            ]

            # Definir formatos de encabezados con colores diferenciados
            header_formats = [
                workbook.add_format({'bold': True, 'font_size': 12, 'bg_color': '#D9E1F2', 'align': 'center', 'border': 1}),
                workbook.add_format({'bold': True, 'font_size': 12, 'bg_color': '#B2DFDB', 'align': 'center', 'border': 1}),
                workbook.add_format({'bold': True, 'font_size': 12, 'bg_color': '#D7CCC8', 'align': 'center', 'border': 1})
            ]

            # Formato para celdas de datos
            cell_format = workbook.add_format({'font_size': 11, 'border': 1})
            cell_center_format = workbook.add_format({'font_size': 11, 'border': 1, 'align': 'center'})

            row = 0  # Controla la fila donde se escribe en el Excel

            # Función para escribir DataFrames en el Excel con formato
            def write_dataframe(title, df, start_row, title_format, header_format):
                """Escribe un DataFrame en el archivo con formato y devuelve la siguiente fila disponible."""
                nonlocal worksheet
                if df.empty:
                    return start_row  # Si está vacío, no escribirlo

                # Reemplazar NaN, None, Inf, -Inf con ""
                df = df.replace([np.nan, None, np.inf, -np.inf], "")

                # Escribir título fusionado con color específico
                col_range = len(df.columns) - 1
                worksheet.merge_range(start_row, 0, start_row, col_range, title, title_format)
                start_row += 1

                # Escribir encabezados con formato diferenciado
                for col_num, column_name in enumerate(df.columns):
                    worksheet.write(start_row, col_num, column_name, header_format)
                start_row += 1

                # Escribir datos con formato
                for i, row_data in df.iterrows():
                    for col_num, value in enumerate(row_data):
                        if isinstance(value, (int, float)) and not pd.isna(value):  # Alinear números al centro
                            worksheet.write(start_row, col_num, value, cell_center_format)
                        else:
                            worksheet.write(start_row, col_num, str(value), cell_format)
                    start_row += 1

                # Ajustar automáticamente el ancho de las columnas basado en la celda más larga
                for col_num, column_name in enumerate(df.columns):
                    max_length = max(df[column_name].astype(str).apply(len).max(), len(column_name))
                    worksheet.set_column(col_num, col_num, max_length + 2)

                return start_row + 2  # Dejar espacio entre tablas

            # Escribir cada DataFrame en la hoja con colores diferenciados
            row = write_dataframe("Información del Pedido", df_pedido, row, title_formats[0], header_formats[0])
            row = write_dataframe("Lista de Productos", df_productos, row, title_formats[1], header_formats[1])


        output.seek(0)
        return output
