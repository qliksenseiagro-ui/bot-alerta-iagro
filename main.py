import os
import asyncio
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd

# =========================================================
# CONFIGURAÇÕES
# =========================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
SERVICE_ACCOUNT_FILE = "service_account.json"

ESTADO_DIR = "estado"
ESTADO_ARQUIVO = os.path.join(ESTADO_DIR, "ultimo_arquivo.txt")

USUARIOS_ARQUIVO = os.path.join(ESTADO_DIR, "usuarios.txt")

# =========================================================
# UTILIDADES DE ESTADO
# =========================================================

def garantir_pasta_estado():
    os.makedirs(ESTADO_DIR, exist_ok=True)


def ler_ultimo_arquivo():
    if not os.path.exists(ESTADO_ARQUIVO):
        return None
    with open(ESTADO_ARQUIVO, "r") as f:
        return f.read().strip()


def salvar_ultimo_arquivo(file_id):
    garantir_pasta_estado()
    with open(ESTADO_ARQUIVO, "w") as f:
        f.write(file_id)


def carregar_usuarios():
    garantir_pasta_estado()
    usuarios = {}
    if not os.path.exists(USUARIOS_ARQUIVO):
        return usuarios

    with open(USUARIOS_ARQUIVO, "r") as f:
        for linha in f:
            chat_id, telefone, ativo = linha.strip().split(";")
            usuarios[telefone] = {
                "chat_id": int(chat_id),
                "ativo": ativo == "1"
            }
    return usuarios


def salvar_usuarios(usuarios):
    garantir_pasta_estado()
    with open(USUARIOS_ARQUIVO, "w") as f:
        for telefone, dados in usuarios.items():
            ativo = "1" if dados["ativo"] else "0"
            f.write(f"{dados['chat_id']};{telefone};{ativo}\n")

# =========================================================
# GOOGLE DRIVE
# =========================================================

def obter_drive_service():
    creds = service_account_
