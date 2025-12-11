import discord
from discord.ext import commands, tasks
import re
import os
from flask import Flask
from threading import Thread
import asyncio # Módulo necessário para o agendamento assíncrono

# =================================================================
#                         ⚠️ CONFIGURAÇÕES ⚠️
# =================================================================

# ID do canal ONDE o bot vai LER os logs (MUITO IMPORTANTE!)
CANAL_SOURCE_ID = 1192144411400872099  
# ID do canal ONDE o bot vai POSTAR/EDITAR a contagem
CANAL_DESTINO_ID = 1448701158272143402 

# =================================================================
#                       VARIÁVEIS DE FILTRAGEM
# =================================================================

NOME_ALVO_RUAN = "Ruan"
NOME_ALVO_ARCAN = "Arcan"

# =================================================================
#                       VARIÁVEIS GLOBAIS E INICIALIZAÇÃO
# =================================================================

# Variável para controlar a mensagem que será editada
MENSAGEM_CONTROLE = None

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# =================================================================
#                   FUNÇÕES DE KEEP-ALIVE (FLASK)
# =================================================================

app = Flask('')

@app.route('/')
def home():
    return "Bot de Logs está Ativo e sendo Pingado!"

def run_flask():
    # Roda o servidor Flask para manter o Render ativo
    app.run(host='0.0.0.0', port=8080, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# =================================================================
#              LÓGICA CENTRAL DE CONTABILIZAÇÃO (FUNÇÃO AUXILIAR)
# =================================================================

async def run_contabilizacao():
    """Função que contém a lógica de leitura, contagem e envio de embeds."""
    global MENSAGEM_CONTROLE

    # Garante que o bot está pronto
    await bot.wait_until_ready() 
    
    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    canal_destino = bot.get_channel(CANAL_DESTINO_ID)

    if not canal_log or not canal_destino:
        print("Erro: Um dos canais (log ou destino) não foi encontrado.")
        return

    compras_ruan = 0
    compras_arcan = 0

    try:
        # Busca as últimas 500 mensagens de log (Limite seguro)
        async for message in canal_log.history(limit=500):
            content = message.content

            if "Purchased" in content and "Rare Fruit Chest" in content:

                quantidade_match = re.search(r"Purchased x(\d+)", content)
                player_match = re.search(r"Player: (\w+)", content)

                if quantidade_match and player_match:
                    quantidade = int(quantidade_match.group(1))
                    player_name = player_match.group(1)

                    if player_name.startswith(NOME_ALVO_RUAN):
                        compras_ruan += quantidade
                    elif player_name.startswith(NOME_ALVO_ARCAN):
                        compras_arcan += quantidade

    except discord.Forbidden:
        print("ERRO: O bot não tem permissão para ler o histórico de mensagens.")
        return
    except Exception as e:
        print(f"Ocorreu um erro durante a leitura do histórico: {e}") 
        return

    # --- MONTAGEM DO EMBED ---
    total_geral = compras_ruan + compras_arcan

    embed = discord.Embed(
        title="🏆 Contagem de Rare Fruit Chests (Últimos 500 Logs)",
        color=discord.Color.red()
    )
    embed.add_field(name=f"📦 Compras de {NOME_ALVO_RUAN} (Contas Ruan*)",
                    value=f"**{compras_ruan}** Rare Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name=f"🐟 Compras de {NOME_ALVO_ARCAN} (Contas Arcan*)",
                    value=f"**{compras_arcan}** Rare Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name="📊 Total Geral do Grupo",
                    value=f"**{total_geral}** Chests.",
                    inline=False)

    embed.set_footer(text="Contagem atualizada a cada 3 minutos. Use !reset para limpar os logs e zerar.")

    # --- ENVIO / EDIÇÃO DA MENSAGEM ---
    try:
        if MENSAGEM_CONTROLE is None:
            MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
        else:
            await MENSAGEM_CONTROLE.edit(embed=embed)

    except discord.NotFound:
        # Se a mensagem de controle foi apagada manualmente
        MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)

    except Exception as e:
        print(f"ERRO ao enviar/editar mensagem no Discord: {e}")

# =================================================================
#              TAREFA DE CONTABILIZAÇÃO (RODA A CADA 3 MINUTOS)
# =================================================================

@tasks.loop(seconds=180) # 180 segundos = 3 minutos
async def contabilizar_e_enviar():
    await run_contabilizacao()

# =================================================================
#                         COMANDO DE RESET (LIMPAR MENSAGENS)
# CORREÇÃO FINAL: Removido o start() manual para evitar o erro 'NoneType'
# =================================================================

@bot.command(name='reset', aliases=['reiniciar', 'limpar'])
async def reset_contagem(ctx):
    global MENSAGEM_CONTROLE

    # 1. VERIFICAÇÃO DE PERMISSÃO
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("🚫 Você não tem permissão de Administrador para usar este comando!")
        return
        
    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    
    if not canal_log:
        await ctx.send("❌ ERRO: Não foi possível encontrar o canal de logs.")
        return

    # Verifica permissão para limpar mensagens (Gerenciar Mensagens)
    if not canal_log.guild.me.guild_permissions.manage_messages:
        await ctx.send(f"🚫 ERRO: O bot não possui a permissão 'Gerenciar Mensagens' no canal {canal_log.mention} para limpar o histórico.")
        return

    # 2. AVISO INICIAL E PARADA DO LOOP
    await ctx.send("🚨 Contagem de Rare Fruit Chests será **REINICIADA**. Limpando **TODAS** as mensagens no canal de logs...")

    was_running = contabilizar_e_enviar.is_running()
    if was_running:
        # Parar para evitar race condition com o purge
        contabilizar_e_enviar.stop()
        
    try:
        # 3. LIMPA TODAS AS MENSAGENS DO CANAL DE LOGS
        mensagens_apagadas = await canal_log.purge(limit=None, check=None)
        
        await ctx.send(f"✅ {len(mensagens_apagadas)} mensagens antigas foram apagadas do canal de logs!")

        # 4. REINICIA O ESTADO DA MENSAGEM
        MENSAGEM_CONTROLE = None
        
        # 5. FORÇA A ATUALIZAÇÃO NO CANAL DE DESTINO (MENSAGEM ZERO)
        # Usa asyncio.create_task para executar a lógica de forma imediata e assíncrona.
        asyncio.create_task(run_contabilizacao())
        
        # O loop automático (tasks.loop) reiniciará sozinho em 180 segundos (3 minutos)
        # Não chamamos .start() manualmente para evitar o bug 'NoneType'.

        await ctx.send("✅ Nova contagem (zero) iniciada e postada com sucesso!")
            
    except discord.Forbidden:
        await ctx.send("🚫 ERRO: O bot não tem permissão para apagar mensagens. Conceda 'Gerenciar Mensagens'.")
    except Exception as e:
        # Garante que o loop volte a rodar caso o 'stop()' o tenha desativado
        if was_running and not contabilizar_e_enviar.is_running():
            contabilizar_e_enviar.start()
        await ctx.send(f"❌ Ocorreu um erro inesperado durante a limpeza ou reinício: {e}")

# =================================================================
#                            RODAR O BOT
# =================================================================

@bot.event
async def on_ready():
    print('--------------------------------------------------')
    print(f'Bot logado como {bot.user}')
    print('--------------------------------------------------')

    if not contabilizar_e_enviar.is_running():
        contabilizar_e_enviar.start()

# O Token é lido de forma segura da variável de ambiente (Render Secrets)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if BOT_TOKEN is None:
    print("ERRO CRÍTICO: Variável BOT_TOKEN não encontrada. O bot não pode iniciar.")
else:
    # 1. Inicia o servidor Flask para o keep-alive
    keep_alive() 
    
    # 2. Inicia o bot do Discord
    print("Iniciando o bot do Discord...")
    
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"Erro Crítico ao iniciar o bot: {e}")
