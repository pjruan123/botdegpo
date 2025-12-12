import discord
from discord.ext import commands, tasks
import re
import asyncio
import os 
from aiohttp import web # Para o servidor Keep-Alive (24/7 no Render)

# =================================================================
#                         ⚠️ CONFIGURAÇÕES ⚠️
# =================================================================

# 🚨 PASSO CRÍTICO: Lê o token da variável de ambiente BOT_TOKEN
# Você DEVE configurar BOT_TOKEN no painel do Render.
BOT_TOKEN = os.environ.get('BOT_TOKEN') 
if not BOT_TOKEN:
    print("ERRO CRÍTICO: A variável de ambiente BOT_TOKEN não foi configurada.")

# IDs de canais
CANAL_SOURCE_ID = 1448778112430116999  
CANAL_DESTINO_ID = 1448701158272143402 

# =================================================================
#                       VARIÁVEIS DE FILTRAGEM
# =================================================================

NOME_ALVO_RUAN = "Ruan"
NOME_ALVO_ARCAN = "Arcan"

# =================================================================
#                       VARIÁVEIS GLOBAIS E INICIALIZAÇÃO
# =================================================================

MENSAGEM_CONTROLE = None

intents = discord.Intents.default()
intents.message_content = True # ESTA INTENÇÃO DEVE ESTAR LIGADA NO PORTAL DO DISCORD
intents.messages = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# =================================================================
#                  >>>>>> SERVIDOR WEB (KEEP-ALIVE) <<<<<<
# =================================================================

async def handle(request):
    """Responde ao ping HTTP para manter o Render ativo."""
    return web.Response(text="Bot is running and counting chests!")

async def start_web_server():
    """Inicia o servidor web em uma task separada."""
    try:
        app = web.Application()
        app.router.add_get('/', handle)
        
        # O Render define a porta na variável de ambiente PORT (usamos 10000 como fallback)
        port = os.environ.get('PORT', 10000) 
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port=port)
        await site.start()
        print(f"✅ Servidor Web (Keep-Alive) iniciado na porta {port}.")
    except Exception as e:
        print(f"❌ ERRO ao iniciar servidor web (Keep-Alive): {e}")

# =================================================================
#              LÓGICA CENTRAL DE CONTABILIZAÇÃO (FUNÇÃO AUXILIAR)
# =================================================================

async def run_contabilizacao():
    """Função que contém a lógica de leitura, contagem e envio de embeds."""
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
            
            # FILTRO: Procura por qualquer "Fruit Chest" e "Purchased"
            if "Fruit Chest" in content and "Purchased" in content:
                
                quantidade = 0
                player_name = ""
                
                # Busca a quantidade (x1, x5, etc.) com case-insensitive
                quantidade_match = re.search(r"Purchased x(\d+)", content, re.IGNORECASE)
                if quantidade_match:
                    quantidade = int(quantidade_match.group(1))
                
                # Busca o nome do jogador (depois de "Player:)
                player_match = re.search(r"Player:([^(]+)", content)
                if player_match:
                    player_name = player_match.group(1).strip()
                    
                    # Trata o formato com parênteses (Player: Nome (ID))
                    if "(" in player_name:
                        player_name = player_name.split("(")[0].strip()
                
                # VERIFICAÇÃO DOS NOMES (RUAN E ARCAN)
                if player_name and quantidade > 0:
                    player_lower = player_name.lower()
                    
                    if "ruan" in player_lower:
                        compras_ruan += quantidade
                        print(f"✅ Contabilizado: {quantidade} baús para Ruan (Player: {player_name})")
                    elif "arcan" in player_lower:
                        compras_arcan += quantidade
                        print(f"✅ Contabilizado: {quantidade} baús para Arcan (Player: {player_name})")
                    else:
                        print(f"⚠️ Ignorado: Player '{player_name}' não contém Ruan nem Arcan")

    except Exception as e:
        print(f"Ocorreu um erro durante a leitura do histórico: {e}") 
        return

    # --- MONTAGEM DO EMBED ---
    total_geral = compras_ruan + compras_arcan

    embed = discord.Embed(
        title="🏆 Contagem de Fruit Chests (Últimos 500 Logs)", 
        color=discord.Color.red()
    )
    embed.add_field(name=f"📦 Compras de {NOME_ALVO_RUAN} (Contas Ruan*)",
                    value=f"**{compras_ruan}** Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name=f"🐟 Compras de {NOME_ALVO_ARCAN} (Contas Arcan*)",
                    value=f"**{compras_arcan}** Fruit Chests compradas.",
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
#                         COMANDO DE RESET (LIMPAR MESSAGENS)
# =================================================================

@bot.command(name='reset', aliases=['reiniciar', 'limpar'])
async def reset_contagem(ctx):
    global MENSAGEM_CONTROLE

    # 1. VERIFICAÇÃO DE PERMISSÃO
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("🚫 Você não tem permissão de Administrador para usar este comando!")
        return

    # Verificação de canal
    if ctx.channel.id != CANAL_DESTINO_ID:
        await ctx.send(f"❌ Este comando só pode ser usado no canal de destino <#{CANAL_DESTINO_ID}>!")
        return

    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    canal_destino = bot.get_channel(CANAL_DESTINO_ID)

    if not canal_log or not canal_destino:
        await ctx.send("❌ ERRO: Não foi possível encontrar um dos canais (source ou destino).")
        return

    # Verificação de permissão de Gerenciar Mensagens
    if not canal_log.guild.me.guild_permissions.manage_messages:
        await ctx.send(f"🚫 ERRO: O bot não possui a permissão 'Gerenciar Mensagens' no canal de logs.")
        return

    # 2. AVISO INICIAL
    mensagem_aviso = await ctx.send("🚨 **CONTAGEM SENDO REINICIADA** 🚨\nLimpando mensagens do canal de logs... Isso pode levar alguns segundos.")

    # Tentativa SEGURA de parar o loop
    if contabilizar_e_enviar.is_running():
        try:
            contabilizar_e_enviar.stop()
        except Exception as e:
            if "'NoneType' object is not callable" not in str(e):
                print(f"❌ Aviso: Erro inesperado ao parar o loop: {e}")
                
    try:
        # 3. LIMPEZA LENTA E SEGURA DAS MENSAGENS
        contador_mensagens = 0
        
        async def apagar_lentamente(limit=None):
            nonlocal contador_mensagens
            apagadas = 0
            
            while True:
                deletadas = await canal_log.purge(limit=50, check=lambda m: True)
                
                if not deletadas:
                    break
                    
                apagadas += len(deletadas)
                contador_mensagens += len(deletadas)
                
                if contador_mensagens % 50 == 0:
                     await mensagem_aviso.edit(content=f"🔄 Limpando... {contador_mensagens} mensagens apagadas até agora.")
                
                await asyncio.sleep(1.5)
                
                if limit and apagadas >= limit:
                    break
                    
            return apagadas
            
        total_apagadas = await apagar_lentamente()
        
        await mensagem_aviso.edit(content=f"✅ **{total_apagadas} mensagens** foram apagadas do canal de logs!")
        await asyncio.sleep(2)

        # 4. REINICIA O ESTADO DA MENSAGEM DE CONTROLE
        if MENSAGEM_CONTROLE:
            try:
                await MENSAGEM_CONTROLE.delete()
            except:
                pass
        MENSAGEM_CONTROLE = None
        
        # 5. ENVIA NOVA MENSAGEM COM CONTAGEM ZERADA
        embed = discord.Embed(
            title="🏆 Contagem de Fruit Chests (REINICIADA)", 
            color=discord.Color.green()
        )
        embed.add_field(name=f"📦 Compras de {NOME_ALVO_RUAN} (Contas Ruan*)",
                        value=f"**0** Fruit Chests compradas.",
                        inline=False)
        embed.add_field(name=f"🐟 Compras de {NOME_ALVO_ARCAN} (Contas Arcan*)",
                        value=f"**0** Fruit Chests compradas.",
                        inline=False)
        embed.add_field(name="📊 Total Geral do Grupo",
                        value=f"**0** Chests.",
                        inline=False)
        embed.set_footer(text="Contagem reiniciada. Canal de logs limpo completamente.")
        
        MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
        
        await mensagem_aviso.edit(content=f"✅ Contagem reiniciada com sucesso! {total_apagadas} mensagens foram limpas.")

    except discord.Forbidden:
        await ctx.send("🚫 ERRO: O bot não tem permissão para apagar mensagens. Conceda 'Gerenciar Mensagens'.")
    except discord.HTTPException as e:
        await ctx.send(f"❌ Erro HTTP ao limpar mensagens: {e}")
    except Exception as e:
        await ctx.send(f"❌ Ocorreu um erro inesperado: {e}")
    finally:
        # Garante que o loop volte a rodar!
        if not contabilizar_e_enviar.is_running():
             try:
                contabilizar_e_enviar.start()
             except Exception as start_err:
                 if "'NoneType' object is not callable" not in str(start_err):
                     print(f"❌ ERRO GRAVE ao tentar reiniciar a tarefa: {start_err}")


# =================================================================
#                            RODAR O BOT
# =================================================================

@bot.event
async def on_ready():
    print('--------------------------------------------------')
    print(f'Bot logado como {bot.user}')
    print('--------------------------------------------------')
    
    # INICIA O SERVIDOR WEB (KEEP-ALIVE)
    asyncio.create_task(start_web_server()) 

    if not contabilizar_e_enviar.is_running():
        contabilizar_e_enviar.start()
        
# Inicia o bot com o Token definido no topo do arquivo.
if not BOT_TOKEN:
    print("ERRO CRÍTICO: Não foi possível obter o BOT_TOKEN das variáveis de ambiente. O bot não irá iniciar.")
else:
    print("Iniciando o bot do Discord usando Variável de Ambiente...")
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"Erro Crítico ao iniciar o bot: {e}")
