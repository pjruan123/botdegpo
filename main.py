import discord
from discord.ext import commands, tasks
import re
import os
from flask import Flask
from threading import Thread

# =================================================================
#                         ⚠️ CONFIGURAÇÕES ⚠️
# =================================================================

# IMPORTANTE: Mude estes IDs para os seus canais.
CANAL_SOURCE_ID = 1192144411400872099  # ID do canal de logs (Feral)
CANAL_DESTINO_ID = 1448701158272143402 # ID do canal ONDE o bot vai POSTAR/EDITAR a contagem

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
    # Resposta para o Render Pinger
    return "Bot de Logs está Ativo e sendo Pingado!"

def run_flask():
    # Roda o servidor Flask em uma Thread separada na porta 8080 (padrão do Replit)
    app.run(host='0.0.0.0', port=8080, debug=False)

def keep_alive():
    # Inicia o servidor Flask em uma Thread para não bloquear o bot do Discord
    t = Thread(target=run_flask)
    t.start()

# =================================================================
#              TAREFA DE CONTABILIZAÇÃO (RODA A CADA 10 SEGUNDOS)
# =================================================================

@tasks.loop(seconds=10)
async def contabilizar_e_enviar():
    global MENSAGEM_CONTROLE

    await bot.wait_until_ready()
    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    canal_destino = bot.get_channel(CANAL_DESTINO_ID)

    if not canal_log or not canal_destino:
        print("Erro: Um dos canais (log ou destino) não foi encontrado.")
        return

    compras_ruan = 0
    compras_arcan = 0

    try:
        # Busca as últimas 500 mensagens de log
        async for message in canal_log.history(limit=500):
            content = message.content

            if "Purchased" in content and "Rare Fruit Chest" in content:

                quantidade_match = re.search(r"Purchased x(\d+)", content)
                player_match = re.search(r"Player: (\w+)", content)

                if quantidade_match and player_match:
                    quantidade = int(quantidade_match.group(1))
                    player_name = player_match.group(1)

                    # LÓGICA DE FILTRO: Conta qualquer nome que comece com o prefixo
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

    embed.set_footer(text="Contagem atualizada a cada 10 segundos. Use !reset para começar uma nova postagem.")

    # --- ENVIO / EDIÇÃO DA MENSAGEM ---
    try:
        if MENSAGEM_CONTROLE is None:
            # Envia uma nova mensagem se for o primeiro ciclo ou após um reset
            MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
            print("Mensagem de controle enviada.")
        else:
            # Edita a mensagem existente
            await MENSAGEM_CONTROLE.edit(embed=embed)
            print("Mensagem de controle atualizada (editada).")

    except discord.NotFound:
        # Se a mensagem original foi apagada manualmente
        MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
        print("Mensagem de controle não encontrada. Enviando nova.")

    except Exception as e:
        print(f"ERRO ao enviar/editar mensagem no Discord: {e}")

# =================================================================
#                         COMANDO DE RESET
# =================================================================

@bot.command(name='reset', aliases=['reiniciar', 'limpar'])
async def reset_contagem(ctx):
    # Proteção: Apenas administradores podem usar o comando
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("🚫 Você não tem permissão de Administrador para usar este comando!")
        return

    global MENSAGEM_CONTROLE

    await ctx.send("🚨 Contagem de Rare Fruit Chests reiniciada. Enviando a nova postagem...")

    # Força o bot a "esquecer" a mensagem antiga, forçando um novo envio no próximo ciclo
    MENSAGEM_CONTROLE = None

    # Força a execução imediata do loop para postar a nova mensagem zerada
    await contabilizar_e_enviar()

    await ctx.send("✅ Nova contagem iniciada e postada com sucesso!")

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

# O Token é lido de forma segura da variável de ambiente no Replit Secrets
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if BOT_TOKEN is None:
    print("ERRO CRÍTICO: Variável BOT_TOKEN não encontrada. O bot não pode iniciar.")
else:
    # Inicia o servidor Flask para manter o bot ativo
    keep_alive()
    
    # Inicia o bot do Discord
    print("Iniciando o bot do Discord...")
    bot.run(BOT_TOKEN)
