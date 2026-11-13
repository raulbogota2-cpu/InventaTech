# Usamos una imagen oficial de Python
FROM python:3.11-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos el archivo de requerimientos primero
COPY requirements.txt .

# Instalamos las dependencias del proyecto
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código del proyecto al directorio de trabajo
COPY . .

# Exponemos el puerto en el que corre Flask
EXPOSE 5000

# Comando para ejecutar la aplicación
CMD ["python", "app.py"]