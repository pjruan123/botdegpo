import discord
from discord.ext import commands, tasks
import re
import asyncio
import os 
import json 
from aiohttp import web 

# =================================================================
#                         ⚠️ CONFIGURAÇÕES ⚠️
# =================================================================

BOT_TOKEN = os.environ.get('BOT_TOKEN') 
if not BOT_TOKEN:
    print("ERRO CRÍTICO: A variável de ambiente BOT_TOKEN não foi configurada.")

# IDs de canais (Use seus IDs reais aqui)
CANAL_SOURCE_ID = 1448778112430116999  
CANAL_DESTINO_ID = 1448701158272143402 
ARQUIVO_DADOS = "contagens.json" 
ARQUIVO_LAST_ID = "last_id.json" # Novo arquivo para salvar o marcador de leitura

# =================================================================
#                       VARIÁVEIS GLOBAIS E INICIALIZAÇÃO
# =================================================================

MENSAGEM_CONTROLE = None
contagens_individuais = {} # { "NomeConta1": 15, "NomeConta2": 30, ... }
last_processed_id = None # ID da última mensagem de log processada

intents = discord.Intents.default()
intents.message_content = True 
intents.messages = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# =================================================================
#                   FUNÇÕES DE PERSISTÊNCIA DE DADOS
# =================================================================

def carregar_dados():
    """Carrega contagens e o ID da última mensagem processada."""
    global contagens_individuais, last_processed_id
    
    # Carrega contagens
    if os.path.exists(ARQUIVO_DADOS):
        try:
            with open(ARQUIVO_DADOS, 'r') as f:
                contagens_individuais = json.load(f).get('contagens', {})
        except Exception as e:
            print(f"❌ Erro ao carregar contagens: {e}")
            
    # Carrega último ID
    if os.path.exists(ARQUIVO_LAST_ID):
        try:
            with open(ARQUIVO_LAST_ID, 'r') as f:
                last_processed_id = json.load(f).get('last_id')
        except Exception as e:
            print(f"❌ Erro ao carregar last_id: {e}")
            
    print(f"✅ Dados carregados. Último ID: {last_processed_id}")


def salvar_dados():
    """Salva contagens e o ID da última mensagem processada."""
    try:
        # Salva contagens
        with open(ARQUIVO_DADOS, 'w') as f:
            salvar = {'contagens': {str(k): v for k, v in contagens_individuais.items()}}
            json.dump(salvar, f, indent=4)
            
        # Salva último ID
        if last_processed_id:
            with open(ARQUIVO_LAST_ID, 'w') as f:
                json.dump({'last_id': last_processed_id}, f)
                
        print("💾 Dados e Last ID salvos com sucesso.")
        
    except Exception as e:
        print(f"❌ Erro ao salvar dados: {e}")

# =================================================================
#                  >>>>>> SERVIDOR WEB (KEEP-ALIVE) <<<<<<
# =================================================================

async def handle(request):
    return web.Response(text="Bot is running and counting chests!")

async def start_web_server():
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
    Lê o histórico *a partir* do último ID processado e atualiza a contagem.
    """
    global MENSAGEM_CONTROLE, contagens_individuais, last_processed_id

    await bot.wait_until_ready() 
    
    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    canal_destino = bot.get_channel(CANAL_DESTINO_ID)

    if not canal_log or not canal_destino:
        print("Erro: Um dos canais (log ou destino) não foi encontrado.")
        return

    novas_mensagens = []
    
    try:
        # Busca o histórico: 500 mensagens *APÓS* o último ID processado
        # Se last_processed_id for None, ele pega as 500 mais recentes
        async for message in canal_log.history(limit=500, after=discord.Object(id=last_processed_id) if last_processed_id else None):
            # Salva apenas mensagens enviadas por BOTs (como webhooks)
            if message.author.bot: 
                novas_mensagens.append(message)
                
        # Inverte a ordem para processar do mais antigo para o mais novo
        novas_mensagens.reverse()
        
        if not novas_mensagens:
            print("Nenhum novo log de bot encontrado.")
            await run_update_embed() # Apenas atualiza o embed
            return

        print(f"Processando {len(novas_mensagens)} novas mensagens de log...")

        # Processa apenas as novas mensagens
        for message in novas_mensagens:
            full_text = message.content or ""
            
            # LÓGICA DE LEITURA BASEADA NA IMAGEM (Embed Description é o foco)
            if message.embeds:
                try:
                    embed = message.embeds[0]
                    if embed.description:
                        full_text += f" {embed.description}"
                    # A imagem não mostra outros campos, então focamos na descrição
                        
                except Exception:
                    continue 

            if not full_text.strip():
                continue

            # 3. PROCESSAMENTO DO CONTEÚDO (REGEX ajustado para o formato da imagem)
            if "Fruit Chest" in full_text and "Purchased" in full_text:
                
                print(f"***** DEBUG TEXT CAPTURADO *****: {full_text[:200].replace('\n', ' ')}")

                quantidade = 0
                player_name_completo = ""
                
                # Regex para quantidade (Purchased x1)
                quantidade_match = re.search(r"Purchased x(\d+)", full_text, re.IGNORECASE)
                if quantidade_match:
                    quantidade = int(quantidade_match.group(1))
                
                # Regex para o nome do jogador (Player: Nome (ID))
                player_match = re.search(r"Player:\s*([^(]+)", full_text, re.IGNORECASE)
                if player_match:
                    player_name_completo = player_match.group(1).strip()
                    if "(" in player_name_completo:
                        player_name_completo = player_name_completo.split("(")[0].strip()
                
                # Rastreamento individual
                if player_name_completo and quantidade > 0:
                    player_lower = player_name_completo.lower()
                    
                    if "ruan" in player_lower or "arcan" in player_lower:
                        
                        contagens_individuais[player_name_completo] = contagens_individuais.get(player_name_completo, 0) + quantidade
                        
                        print(f"✅ Contabilizado: {quantidade} baús para {player_name_completo}.")
                        
            # 4. ATUALIZA O MARCADOR
            last_processed_id = message.id
            salvar_dados()

    except discord.Forbidden:
        print("ERRO: O bot não tem permissão para ler o canal de logs.")
    except Exception as e:
        print(f"Ocorreu um erro durante a leitura do histórico: {e}") 
        
    # 5. Atualiza o Embed no canal de destino
    await run_update_embed()


async def run_update_embed():
    """Função separada para atualizar o Embed de contagem."""
    global MENSAGEM_CONTROLE
    
    canal_destino = bot.get_channel(CANAL_DESTINO_ID)
    if not canal_destino:
        return

    # Recalcula as somas totais do Ruan/Arcan com base nos dados salvos
    total_ruan = sum(v for k, v in contagens_individuais.items() if NOME_ALVO_RUAN.lower() in k.lower())
    total_arcan = sum(v for k, v in contagens_individuais.items() if NOME_ALVO_ARCAN.lower() in k.lower())
    total_geral = total_ruan + total_arcan
    
    embed = discord.Embed(
        title="🏆 Contagem de Fruit Chests (Total Acumulado)", 
        color=discord.Color.red()
    )
    embed.add_field(name=f"📦 Compras de Ruan*",
                    value=f"**{total_ruan}** Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name=f"🐟 Compras de Arcan*",
                    value=f"**{total_arcan}** Fruit Chests compradas.",
                    inline=False)
    embed.add_field(name="📊 Total Geral do Grupo",
                    value=f"**{total_geral}** Chests.",
                    inline=False)

    embed.set_footer(text=f"Contagem acumulada. Último log processado: {last_processed_id}")

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
#                         COMANDOS
# =================================================================

@bot.command(name='listar', aliases=['conta'])
async def listar_conta(ctx, *, nome_da_conta: str):
    """Lista a contagem total de baús de uma conta específica."""
    
    if nome_da_conta in contagens_individuais:
        total = contagens_individuais[nome_da_conta]
        await ctx.send(f"✅ A conta **{nome_da_conta}** acumulou **{total}** Fruit Chests.")
        return
        
    matches = {k: v for k, v in contagens_individuais.items() if nome_da_conta.lower() in k.lower()}
    
    if matches:
        response = [f"Contas encontradas que contêm '{nome_da_conta}':"]
        for nome, total in list(matches.items())[:10]:
            response.append(f"• **{nome}**: {total} Chests")
        
        await ctx.send('\n'.join(response))
    else:
        await ctx.send(f"❌ Nenhuma contagem encontrada para contas que contenham **'{nome_da_conta}'**.")


@bot.command(name='reset', aliases=['reiniciar', 'limpar'])
async def reset_contagem(ctx):
    global MENSAGEM_CONTROLE, contagens_individuais, last_processed_id

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("🚫 Você não tem permissão de Administrador para usar este comando!")
        return
        
    canal_log = bot.get_channel(CANAL_SOURCE_ID)
    
    mensagem_aviso = await ctx.send("🚨 **CONTAGEM SENDO REINICIADA** 🚨\nLimpando mensagens e **ZERANDO OS DADOS DE CONTAGEM**...")

    if contabilizar_e_enviar.is_running():
        try:
            contabilizar_e_enviar.stop()
        except Exception:
            pass
            
    try:
        # 3. ZERA E SALVA DADOS NOVOS
        contagens_individuais = {}
        last_processed_id = None # ZERA O MARCADOR
        salvar_dados() 

        # 4. LIMPEZA DE MENSAGENS (Opcional, mas mantém a base limpa)
        total_apagadas = 0
        if canal_log and canal_log.guild.me.guild_permissions.manage_messages:
            total_apagadas = await canal_log.purge(limit=500) 
            await asyncio.sleep(2)

        # 5. REINICIA O ESTADO DA MENSAGEM DE CONTROLE
        if MENSAGEM_CONTROLE:
            try:
                await MENSAGEM_CONTROLE.delete()
            except:
                pass
        MENSAGEM_CONTROLE = None
        
        # 6. ENVIA NOVA MENSAGEM COM CONTAGEM ZERADA
        await run_update_embed()
        
        await mensagem_aviso.edit(content=f"✅ Contagem e dados zerados. {total_apagadas} mensagens limpas.")

    except Exception as e:
        await ctx.send(f"❌ Ocorreu um erro inesperado: {e}")
    finally:
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
    
    carregar_dados() 
    
    asyncio.create_task(start_web_server()) 

    if not contabilizar_e_enviar.is_running():
        contabilizar_e_enviar.start()
        
if not BOT_TOKEN:
    print("ERRO CRÍTICO: Não foi possível obter o BOT_TOKEN.")
else:
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"Erro Crítico ao iniciar o bot: {e}")
