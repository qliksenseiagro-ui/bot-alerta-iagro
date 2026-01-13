import os
import asyncio
from telegram import Bot
from telegram import Update
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

# ======================================================
# CONFIGURAÇÕES
# ======================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

SERVICE_ACCOUNT_FILE = "service_account.json"

ESTADO_ARQUIVO = "ultimo_arquivo.txt"
USUARIOS_ARQUIVO = "usuarios.txt"

# ======================================================
# ESTADO
# ======================================================

def ler_ultimo_arquivo():
    if not os.path.exists(ESTADO_ARQUIVO):
        return None
    with open(ESTADO_ARQUIVO, "r") as f:
        return f.read().strip()


def salvar_ultimo_arquivo(file_id):
    with open(ESTADO_ARQUIVO, "w") as f:
        f.write(file_id)


def carregar_usuarios():
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
    with open(USUARIOS_ARQUIVO, "w") as f:
        for telefone, dados in usuarios.items():
            ativo = "1" if dados["ativo"] else "0"
            f.write(f"{dados['chat_id']};{telefone};{ativo}\n")

# ======================================================
# GOOGLE DRIVE
# ======================================================

import json
from google.oauth2 import service_account

def obter_drive_service():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)



def obter_ultimo_arquivo_drive():
    service = obter_drive_service()
    r = service.files().list(
        q=f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and name='AlertaIAGRO.xlsx'",
        orderBy="createdTime desc",
        pageSize=1,
        fields="files(id, name, createdTime)"
    ).execute()

    arquivos = r.get("files", [])
    return arquivos[0] if arquivos else None


def baixar_arquivo(file_id):
    service = obter_drive_service()
    request = service.files().get_media(fileId=file_id)
    with open("alerta.xlsx", "wb") as f:
        f.write(request.execute())

# ======================================================
# TELEGRAM — HANDLERS
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Bem-vindo ao Bot de Alertas IAGRO*\n\n"
        "Envie seu telefone no formato:\n"
        "`67999999999`\n\n"
        "❌ Para parar alertas, envie:\n"
        "`/parar`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def parar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuarios = carregar_usuarios()
    chat_id = update.message.chat_id

    for tel in usuarios:
        if usuarios[tel]["chat_id"] == chat_id:
            usuarios[tel]["ativo"] = False
            salvar_usuarios(usuarios)
            await update.message.reply_text("🔕 Alertas desativados.")
            return

    await update.message.reply_text("⚠️ Você não estava cadastrado.")


async def receber_telefone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text.strip()

    if not telefone.isdigit() or len(telefone) < 10:
        await update.message.reply_text("❌ Envie no formato: 67999999999")
        return

    usuarios = carregar_usuarios()
    usuarios[telefone] = {
        "chat_id": update.message.chat_id,
        "ativo": True
    }
    salvar_usuarios(usuarios)

    await update.message.reply_text("✅ Cadastro realizado com sucesso!")

# ======================================================
# ENVIO DE ALERTAS (BATCH)
# ======================================================

async def enviar_alertas():
    print("🔎 Verificando Google Drive...")

    ultimo_processado = ler_ultimo_arquivo()
    arquivo = obter_ultimo_arquivo_drive()

    if not arquivo:
        print("ℹ️ Nenhum arquivo encontrado.")
        return

    if arquivo["id"] == ultimo_processado:
        print("ℹ️ Arquivo já processado.")
        return

    baixar_arquivo(arquivo["id"])
    df = pd.read_excel("alerta.xlsx")

    usuarios = carregar_usuarios()
    bot = Bot(token=TELEGRAM_TOKEN)

    for _, linha in df.iterrows():
        telefone = str(linha["Fone"]).strip()
        texto = str(linha["Texto"]).strip()

        if telefone in usuarios and usuarios[telefone]["ativo"]:
            try:
                await bot.send_message(
                    chat_id=usuarios[telefone]["chat_id"],
                    text=texto
                )
            except Exception as e:
                print(f"Erro envio {telefone}: {e}")

    salvar_ultimo_arquivo(arquivo["id"])
    print("✅ Alertas enviados.")

# ======================================================
# MAIN
# ======================================================

async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parar", parar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_telefone))

    # Execução batch (GitHub Actions)
    await enviar_alertas()


if __name__ == "__main__":
    asyncio.run(main())
