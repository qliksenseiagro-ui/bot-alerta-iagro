import os
import json
import asyncio
import pandas as pd
import google.auth
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Carrega variáveis do arquivo .env
load_dotenv()

# ======================================================
# CONFIGURAÇÕES (Variáveis de Ambiente)
# ======================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
# O JSON da Service Account pode vir de uma variável ou de um arquivo real
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT")

ESTADO_ARQUIVO = "ultimo_arquivo.txt"
USUARIOS_ARQUIVO = "usuarios.txt"

# ======================================================
# GESTÃO DE ARQUIVOS LOCAIS
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
            if ";" in linha:
                parts = linha.strip().split(";")
                if len(parts) == 3:
                    chat_id, telefone, ativo = parts
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
# INTEGRAÇÃO GOOGLE DRIVE
# ======================================================



def obter_drive_service():
    import google.auth
    from googleapiclient.discovery import build

    # Escopo explícito de leitura do Drive
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    
    # Criamos as credenciais garantindo que o escopo seja aplicado
    creds, project = google.auth.default()
    if creds.requires_scopes:
        creds = creds.with_scopes(scopes)
    
    # Construímos o serviço com discovery estático desativado para evitar erros de timeout
    return build("drive", "v3", credentials=creds, static_discovery=False)

async def enviar_alertas(context: ContextTypes.DEFAULT_TYPE = None):
    """Função que verifica o Drive e envia mensagens"""
    print("🔎 Verificando Google Drive...")
    try:
        service = obter_drive_service()
        ultimo_processado = ler_ultimo_arquivo()

        # Busca o arquivo mais recente chamado AlertaIAGRO.xlsx
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and name='AlertaIAGRO.xlsx' and trashed=false"
        r = service.files().list(
            q=query,
            orderBy="createdTime desc",
            pageSize=1,
            fields="files(id, name, createdTime)"
        ).execute()

        arquivos = r.get("files", [])
        if not arquivos:
            print("ℹ️ Nenhum arquivo encontrado no Drive.")
            return

        arquivo = arquivos[0]
        if arquivo["id"] == ultimo_processado:
            print(f"ℹ️ Arquivo {arquivo['id']} já foi processado anteriormente.")
            return

        # Download
        print(f"📥 Baixando novo arquivo: {arquivo['name']}...")
        request = service.files().get_media(fileId=arquivo["id"])
        with open("alerta.xlsx", "wb") as f:
            f.write(request.execute())

        # Processamento Excel
        df = pd.read_excel("alerta.xlsx")
        usuarios = carregar_usuarios()
        
        # Se for chamado via job_queue, o bot está no context. Se manual, usa o token
        bot = context.bot if context else Bot(token=TELEGRAM_TOKEN)

        envios_sucesso = 0
        for _, linha in df.iterrows():
            telefone = str(linha["Fone"]).strip()
            texto = str(linha["Texto"]).strip()

            if telefone in usuarios and usuarios[telefone]["ativo"]:
                try:
                    await bot.send_message(
                        chat_id=usuarios[telefone]["chat_id"],
                        text=texto,
                        parse_mode="Markdown"
                    )
                    envios_sucesso += 1
                except Exception as e:
                    print(f"❌ Erro ao enviar para {telefone}: {e}")

        salvar_ultimo_arquivo(arquivo["id"])
        print(f"✅ Processamento concluído. {envios_sucesso} alertas enviados.")

    except Exception as e:
        print(f"💥 Erro crítico no loop de alertas: {e}")

# ======================================================
# HANDLERS DO TELEGRAM
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Bem-vindo ao Bot de Alertas IAGRO*\n\n"
        "Envie seu telefone no formato:\n"
        "`67999999999` (apenas números)\n\n"
        "❌ Para parar os alertas, envie: /parar"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def parar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuarios = carregar_usuarios()
    chat_id = update.message.chat_id
    encontrado = False

    for tel in usuarios:
        if usuarios[tel]["chat_id"] == chat_id:
            usuarios[tel]["ativo"] = False
            encontrado = True
    
    if encontrado:
        salvar_usuarios(usuarios)
        await update.message.reply_text("🔕 Alertas desativados com sucesso.")
    else:
        await update.message.reply_text("⚠️ Você não está cadastrado ou já está inativo.")

async def receber_telefone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text.strip()

    if not telefone.isdigit() or len(telefone) < 10:
        await update.message.reply_text("❌ Formato inválido. Envie apenas números com DDD (ex: 67999998888).")
        return

    usuarios = carregar_usuarios()
    usuarios[telefone] = {
        "chat_id": update.message.chat_id,
        "ativo": True
    }
    salvar_usuarios(usuarios)
    await update.message.reply_text(f"✅ Telefone {telefone} cadastrado! Você receberá alertas assim que o sistema detectar novos arquivos.")

# ======================================================
# INICIALIZAÇÃO
# ======================================================

if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        print("❌ ERRO: TELEGRAM_TOKEN não configurado no .env")
        exit(1)

    print("🤖 Iniciando Bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parar", parar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_telefone))

    # Agendamento: Verifica o Drive a cada 15 minutos (900 segundos)
    # first=10 faz a primeira verificação 10 segundos após ligar o bot
    app.job_queue.run_repeating(enviar_alertas, interval=900, first=10)

    print("📡 Bot online. Aguardando mensagens e verificando Drive a cada 15 min...")
    app.run_polling()