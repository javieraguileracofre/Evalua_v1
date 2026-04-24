# passenger_wsgi.py - cPanel WSGI loader para EvaluaPOS

import os
import sys

# Ruta absoluta a la carpeta raíz del proyecto en el servidor
PROJECT_PATH = "/home2/evaluaso/evaluapos"

if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# Ahora podemos importar el paquete "app"
from app.main import app as application
