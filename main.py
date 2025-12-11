import discord
from discord.ext import commands, tasks
import re
import os  # Necessário para ler o Token da variável de ambiente do Render

# =================================================================
#                         ⚠️ CONFIGURAÇÕES ⚠️
# =================================================================

# ID do canal de logs (Feral)
CANAL_SOURCE_ID = 1192144411400872099
# ID do canal ONDE o bot vai POSTAR/EDITAR a contagem
CANAL_DESTINO_ID = 1448701158272143402

# =================================================================
#                       VARIÁVEIS DE FILTRAGEM
# =================================================================

# Usamos o prefixo mais curto para pegar todas as variações das contas
NOME_ALVO_RUAN = "Ruan"
NOME_ALVO_ARCAN = "Arcan"

# =================================================================
#                       VARIÁVEIS GLOBAIS E INICIALIZAÇÃO
# =================================================================

MENSAGEM_CONTROLE = None

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

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
        # Pega as últimas 500 mensagens do canal de logs
        async for message in canal_log.history(limit=500):
            content = message.content

            # Filtra por itens comprados
            if "Purchased" in content and "Rare Fruit Chest" in content:

                quantidade_match = re.search(r"Purchased x(\d+)", content)
                player_match = re.search(r"Player: (\w+)", content)

                if quantidade_match and player_match:
                    quantidade = int(quantidade_match.group(1))
                    player_name = player_match.group(1)

                    # === LÓGICA DE FILTRO ===
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
    embed.add_field(name=f"📦 Compras de {NOME_ALVO_RUAN} (Todas as Contas)",
                    value=f"**{compras_ruan}** Rare Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name=f"🐟 Compras de {NOME_ALVO_ARCAN} (Todas as Contas)",
                    value=f"**{compras_arcan}** Rare Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name="📊 Total Geral do Grupo",
                    value=f"**{total_geral}** Chests.",
                    inline=False)

    embed.set_footer(text="Contagem atualizada a cada 10 segundos. O bot não contabiliza Logs perdidos ou excluídos.")

    # --- ENVIO / EDIÇÃO DA MENSAGEM ---
    try:
        if MENSAGEM_CONTROLE is None:
            # Envia a primeira mensagem e armazena a referência
            MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
            print("Mensagem de controle enviada.")
        else:
            # Edita a mensagem existente
            await MENSAGEM_CONTROLE.edit(embed=embed)
            print("Mensagem de controle atualizada (editada).")

    except discord.NotFound:
        # Se a mensagem foi apagada, envia uma nova
        MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
        print("Mensagem de controle não encontrada. Enviando nova.")

    except Exception as e:
        print(f"ERRO ao enviar/editar mensagem no Discord: {e}")


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

# --- BLOCO DE INICIALIZAÇÃO SEGURA PARA O RENDER ---

# O token é lido da variável de ambiente 'BOT_TOKEN' configurada no painel do Render.
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if BOT_TOKEN is None:
    print("ERRO CRÍTICO: Variável BOT_TOKEN não encontrada. Configure-a no painel do Render.")
else:
    print("Token lido com sucesso. Tentando conectar ao Discord...")
    # Inicia o bot
    bot.run(BOT_TOKEN)
