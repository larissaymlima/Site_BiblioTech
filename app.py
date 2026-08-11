# --- BIBLIOTECAS ---
import os
import secrets
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
from datetime import timedelta
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Carrega variáveis de ambiente do arquivo .env (SECRET_KEY, DB_*, TWILIO_*, etc.)
load_dotenv()

app = Flask(__name__)

# --- CONFIGURAÇÕES DE SEGURANÇA DO COOKIE DE SESSÃO ---
# SESSION_COOKIE_SECURE só força HTTPS em produção; em teste local (Thunder
# Client via http://127.0.0.1) fica False, senão o cookie de sessão nem seria
# enviado pelo cliente.
app.config['SESSION_COOKIE_SECURE'] = True if os.getenv('FLASK_ENV') == 'production' or os.getenv('USE_HTTPS') == 'true' else False
app.config['SESSION_COOKIE_HTTPONLY'] = True   # JS não consegue ler o cookie (proteção XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Proteção básica contra CSRF via cookie
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # Sessão expira após 8h