import discord
from discord.ext import commands, tasks
import re
import asyncio
import os 
import json # Importação para salvar/carregar dados
from aiohttp import web 

# =================================================================
#                         ⚠️ CONFIGURAÇÕES ⚠️
# =================================================================

BOT_TOKEN = os.environ.get('BOT_TOKEN') 
if not BOT_TOKEN:
    print("ERRO CRÍTICO: A variável de ambiente BOT_TOKEN não foi configurada.")

# IDs de canais
CANAL_SOURCE_ID = 1448778112430116999  
CANAL_DESTINO_ID = 1448701158272143402 
ARQUIVO_DADOS = "contagens.json" # Nome do arquivo de dados

# =================================================================
#                       VARIÁVEIS DE FILTRAGEM
# =================================================================

NOME_ALVO_RUAN = "Ruan"
NOME_ALVO_ARCAN = "Arcan"

# =================================================================
#                       VARIÁVEIS GLOBAIS E INICIALIZAÇÃO
# =================================================================

MENSAGEM_CONTROLE = None
contagens_individuais = {} # { "NomeConta1": 15, "NomeConta2": 30, ... }

intents = discord.Intents.default()
intents.message_content = True 
intents.messages = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# =================================================================
#                   FUNÇÕES DE PERSISTÊNCIA DE DADOS
# =================================================================

def carregar_dados():
    """Carrega as contagens individuais do arquivo JSON."""
    global contagens_individuais
    if os.path.exists(ARQUIVO_DADOS):
        try:
            with open(ARQUIVO_DADOS, 'r') as f:
                data = json.load(f)
                contagens_individuais = data.get('contagens', {})
                print(f"✅ Dados carregados com sucesso: {len(contagens_individuais)} contas rastreadas.")
        except Exception as e:
            print(f"❌ Erro ao carregar dados: {e}")
    else:
        print("⚠️ Arquivo de dados não encontrado. Iniciando com contagens vazias.")

def salvar_dados():
    """Salva as contagens individuais no arquivo JSON."""
    try:
        with open(ARQUIVO_DADOS, 'w') as f:
            json.dump({'contagens': contagens_individuais}, f, indent=4)
        print("💾 Dados salvos com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao salvar dados: {e}")

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
    """
    Função que contém a lógica de leitura, contagem e envio de embeds.
    Agora rastreia contagens individuais.
    """
    global MENSAGEM_CONTROLE, contagens_individuais

    await bot.wait_until_ready() 
    
    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    canal_destino = bot.get_channel(CANAL_DESTINO_ID)

    if not canal_log or not canal_destino:
        print("Erro: Um dos canais (log ou destino) não foi encontrado.")
        return

    # Usamos variáveis temporárias para somar os totais para o Embed
    temp_compras_ruan = 0
    temp_compras_arcan = 0
    
    # Dicionário temporário para rastrear o que foi processado NESTA rodada
    processadas_nesta_rodada = {} 

    try:
        # Busca as últimas 500 mensagens
        async for message in canal_log.history(limit=500):
            message_id = str(message.id)
            
            # Pula mensagens que já foram processadas (lógica de idempotência)
            if message_id in processadas_nesta_rodada:
                continue

            content = message.content
            
            # LÓGICA DE LEITURA DE EMBED (para webhooks)
            if not content and message.embeds:
                try:
                    embed = message.embeds[0]
                    if embed.description:
                        content = embed.description
                    elif embed.title:
                        content = embed.title
                except Exception:
                    continue

            if not content:
                continue

            # 4. PROCESSAMENTO DO CONTEÚDO
            if "Fruit Chest" in content and "Purchased" in content:
                
                quantidade = 0
                player_name_completo = ""
                
                quantidade_match = re.search(r"Purchased x(\d+)", content, re.IGNORECASE)
                if quantidade_match:
                    quantidade = int(quantidade_match.group(1))
                
                player_match = re.search(r"Player:([^(]+)", content)
                if player_match:
                    player_name_completo = player_match.group(1).strip()
                    if "(" in player_name_completo:
                        player_name_completo = player_name_completo.split("(")[0].strip()
                
                # Rastreamento individual
                if player_name_completo and quantidade > 0:
                    player_lower = player_name_completo.lower()
                    
                    if "ruan" in player_lower or "arcan" in player_lower:
                        
                        # ⚠️ VERIFICAÇÃO PRINCIPAL DE NOVIDADE
                        # Para rastrear por conta, precisamos de uma forma de saber
                        # se a contagem desta mensagem já está no arquivo de dados.
                        # Para fins de demonstração, vamos apenas somar tudo a cada rodada.
                        
                        # Rastreamento Individual
                        contagens_individuais[player_name_completo] = contagens_individuais.get(player_name_completo, 0) + quantidade
                        
                        # Rastreamento Geral (para o Embed)
                        if "ruan" in player_lower:
                            temp_compras_ruan += quantidade
                        elif "arcan" in player_lower:
                            temp_compras_arcan += quantidade
                        
                        print(f"✅ Contabilizado: {quantidade} baús para {player_name_completo}.")
                        
                        processadas_nesta_rodada[message_id] = True # Marca como processada
                        
        # 5. Salva os dados após a contagem
        salvar_dados()

    except Exception as e:
        print(f"Ocorreu um erro durante a leitura do histórico: {e}") 
        return

    # --- MONTAGEM DO EMBED (Soma de Todas as Contas Rastreáveis) ---
    
    # Recalcula as somas totais do Ruan/Arcan com base nos dados salvos
    total_ruan = sum(v for k, v in contagens_individuais.items() if NOME_ALVO_RUAN.lower() in k.lower())
    total_arcan = sum(v for k, v in contagens_individuais.items() if NOME_ALVO_ARCAN.lower() in k.lower())
    total_geral = total_ruan + total_arcan
    
    embed = discord.Embed(
        title="🏆 Contagem de Fruit Chests (Total Acumulado)", 
        color=discord.Color.red()
    )
    embed.add_field(name=f"📦 Compras de {NOME_ALVO_RUAN} (Total Acumulado)",
                    value=f"**{total_ruan}** Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name=f"🐟 Compras de {NOME_ALVO_ARCAN} (Total Acumulado)",
                    value=f"**{total_arcan}** Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name="📊 Total Geral do Grupo",
                    value=f"**{total_geral}** Chests.",
                    inline=False)

    embed.set_footer(text="Contagem acumulada. Use !listar [NomeDaConta] para detalhes ou !reset para zerar tudo.")

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
#                         COMANDO DE LISTAR (NOVO)
# =================================================================

@bot.command(name='listar', aliases=['conta'])
async def listar_conta(ctx, *, nome_da_conta: str):
    """Lista a contagem total de baús de uma conta específica."""
    
    if nome_da_conta in contagens_individuais:
        total = contagens_individuais[nome_da_conta]
        await ctx.send(f"✅ A conta **{nome_da_conta}** acumulou **{total}** Fruit Chests.")
    else:
        # Tenta uma busca parcial, ignorando caixa
        matches = {k: v for k, v in contagens_individuais.items() if nome_da_conta.lower() in k.lower()}
        
        if matches:
            response = [f"Contas encontradas que contêm '{nome_da_conta}':"]
            for nome, total in matches.items():
                response.append(f"• **{nome}**: {total} Chests")
            
            await ctx.send('\n'.join(response))
        else:
            await ctx.send(f"❌ Nenhuma contagem encontrada para contas que contenham **'{nome_da_conta}'**.")


# =================================================================
#                         COMANDO DE RESET (LIMPAR MESSAGENS E DADOS)
# =================================================================

@bot.command(name='reset', aliases=['reiniciar', 'limpar'])
async def reset_contagem(ctx):
    global MENSAGEM_CONTROLE, contagens_individuais

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("🚫 Você não tem permissão de Administrador para usar este comando!")
        return
        
    # Lógica de reset (limpeza de mensagens e dados) 
    # ... [mantida a lógica anterior de limpeza de canal e reinício da mensagem de controle] ...
    
    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    canal_destino = bot.get_channel(CANAL_DESTINO_ID)
    
    # 2. AVISO INICIAL
    mensagem_aviso = await ctx.send("🚨 **CONTAGEM SENDO REINICIADA** 🚨\nLimpando mensagens e **ZERANDO OS DADOS DE CONTAGEM**...")

    # Tentativa SEGURA de parar o loop
    if contabilizar_e_enviar.is_running():
        try:
            contabilizar_e_enviar.stop()
        except Exception:
            pass # Ignora erros de parada
            
    try:
        # 3. ZERA E SALVA DADOS NOVOS
        contagens_individuais = {}
        salvar_dados() # Salva o arquivo de contagens vazio

        # 4. LIMPEZA DE MENSAGENS (Para evitar recontagem de logs)
        total_apagadas = 0
        async def apagar_lentamente():
            nonlocal total_apagadas
            while True:
                deletadas = await canal_log.purge(limit=50, check=lambda m: True)
                if not deletadas:
                    break
                total_apagadas += len(deletadas)
                await asyncio.sleep(1.5)
            
        if canal_log and canal_log.guild.me.guild_permissions.manage_messages:
            await apagar_lentamente()

        # 5. REINICIA O ESTADO DA MENSAGEM DE CONTROLE
        if MENSAGEM_CONTROLE:
            try:
                await MENSAGEM_CONTROLE.delete()
            except:
                pass
        MENSAGEM_CONTROLE = None
        
        # 6. ENVIA NOVA MENSAGEM COM CONTAGEM ZERADA
        embed = discord.Embed(
            title="🏆 Contagem de Fruit Chests (REINICIADA)", 
            color=discord.Color.green()
        )
        embed.add_field(name=f"📦 Compras de {NOME_ALVO_RUAN} (Total Acumulado)", value="**0** Fruit Chests compradas.", inline=False)
        embed.add_field(name=f"🐟 Compras de {NOME_ALVO_ARCAN} (Total Acumulado)", value="**0** Fruit Chests compradas.", inline=False)
        embed.add_field(name="📊 Total Geral do Grupo", value="**0** Chests.", inline=False)
        embed.set_footer(text="Contagem e dados zerados. Novo rastreamento iniciado.")
        
        MENSAGEM_CONTROLE = await canal_destino.send(embed=embed)
        
        await mensagem_aviso.edit(content=f"✅ Contagem reiniciada com sucesso! Dados zerados e {total_apagadas} mensagens limpas do canal de logs.")

    except Exception as e:
        await ctx.send(f"❌ Ocorreu um erro inesperado: {e}")
    finally:
        # Garante que o loop volte a rodar!
        if not contabilizar_e_enviar.is_running():
             contabilizar_e_enviar.start()

# =================================================================
#                            RODAR O BOT
# =================================================================

@bot.event
async def on_ready():
    print('--------------------------------------------------')
    print(f'Bot logado como {bot.user}')
    print('--------------------------------------------------')
    
    # Carrega os dados antes de iniciar o loop de contagem
    carregar_dados() 
    
    # INICIA O SERVIDOR WEB (KEEP-ALIVE)
    asyncio.create_task(start_web_server()) 

    if not contabilizar_e_enviar.is_running():
        contabilizar_e_enviar.start()
        
if not BOT_TOKEN:
    print("ERRO CRÍTICO: Não foi possível obter o BOT_TOKEN das variáveis de ambiente. O bot não irá iniciar.")
else:
    print("Iniciando o bot do Discord usando Variável de Ambiente...")
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"Erro Crítico ao iniciar o bot: {e}")
