import os
# ...
# O token é lido da variável de ambiente no Render
BOT_TOKEN = os.environ.get("MTIwMDI5NDAxNTk2NzQzMjc5NA.G3-9mR.aqtq5EWX9lGyCw6QVBcM-WR_yS1imw9sFfuWL8")
import discord
from discord.ext import commands, tasks
import re

# =================================================================
#                         ⚠️ CONFIGURAÇÕES ⚠️
# =================================================================

CANAL_SOURCE_ID = 1192144411400872099  # ID do canal de logs (Feral)
CANAL_DESTINO_ID = 1448701158272143402 # <<< ID do canal ONDE o bot vai POSTAR/EDITAR a contagem
 

# =================================================================
#                       VARIÁVEIS DE FILTRAGEM (AJUSTADO)
# =================================================================

# Usamos o prefixo mais curto para pegar todas as variações das contas
NOME_ALVO_RUAN = "Ruan"       
NOME_ALVO_ARCAN = "Arcan"     # <<< AJUSTADO PARA PEGAR TODAS AS CONTAS ARCAN*

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
        async for message in canal_log.history(limit=500):
            content = message.content
            
            if "Purchased" in content and "Rare Fruit Chest" in content:
                
                quantidade_match = re.search(r"Purchased x(\d+)", content)
                player_match = re.search(r"Player: (\w+)", content)
                
                if quantidade_match and player_match:
                    quantidade = int(quantidade_match.group(1))
                    player_name = player_match.group(1)
                    
                    # === LÓGICA DE FILTRO ATUALIZADA ===
                    if player_name.startswith(NOME_ALVO_RUAN):
                        compras_ruan += quantidade
                    elif player_name.startswith(NOME_ALVO_ARCAN): # <<< FILTRA QUALQUER NOME QUE COMECE COM 'Arcan'
                        compras_arcan += quantidade
                    # ==================================

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
                    value=f"**{compras_arcan}** Rare Fruit Chests compradas.", # <<< NOME NO EMBED AJUSTADO
                    inline=False)
    embed.add_field(name="📊 Total Geral do Grupo", 
                    value=f"**{total_geral}** Chests.", 
                    inline=False)
    
    embed.set_footer(text="Contagem atualizada a cada 10 segundos. O bot não contabiliza Logs perdidos ou excluídos.")

    # --- ENVIO / EDIÇÃO DA MENSAGEM ---
    try:
        if MENSAGEM_CONTROLE is None:
            MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
            print("Mensagem de controle enviada.")
        else:
            await MENSAGEM_CONTROLE.edit(embed=embed)
            print("Mensagem de controle atualizada (editada).")
            
    except discord.NotFound:
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
BOT_TOKEN = "MTIwMDI5NDAxNTk2NzQzMjc5NA.G3-9mR.aqtq5EWX9lGyCw6QVBcM-WR_yS1imw9sFfuWL8" 
bot.run(BOT_TOKEN)
