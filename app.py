import discord
import asyncio
import datetime
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID"))
RADIO_URL = os.getenv("RADIO_URL")

# Configuration des intents
intents = discord.Intents.default()
intents.members = True  # Activer l'intent pour accéder aux membres

# Initialisation du bot avec les commandes slash
class RadioBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.voice_client = None
        self.start_time = None
        self.current_status_index = 0
    
    async def setup_hook(self):
        # Synchroniser les commandes slash avec Discord
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("Commandes slash synchronisées!")

bot = RadioBot()
bot.remove_command("help")  # Supprimer la commande d'aide par défaut

# Variables pour les statistiques
volume_level = 0.1  # 30% par défaut

async def connect_to_channel_and_play():
    """Fonction pour se connecter au salon et jouer la radio"""
    global volume_level
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        channel = discord.utils.get(guild.voice_channels, id=VOICE_CHANNEL_ID)
        if channel:
            try:
                # Se connecter au canal vocal
                if bot.voice_client and bot.voice_client.is_connected():
                    await bot.voice_client.disconnect()
                
                bot.voice_client = await channel.connect()
                
                # Configurer la lecture audio avec reconnexion automatique
                while True:
                    try:
                        # Créer la source audio avec options de reconnexion
                        audio = discord.FFmpegPCMAudio(
                            RADIO_URL, 
                            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
                        )
                        
                        # Appliquer le volume
                        audio_with_volume = discord.PCMVolumeTransformer(audio, volume=volume_level)
                        
                        # Démarrer la lecture
                        bot.voice_client.play(audio_with_volume)
                        print(f"Lecture de la radio : {RADIO_URL} à {volume_level * 100}%")
                        
                        # Attendre que la lecture se termine (ou soit interrompue)
                        while bot.voice_client.is_playing():
                            await asyncio.sleep(1)
                        
                        # Petite pause avant de redémarrer
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        print(f"Erreur lors de la lecture: {e}")
                        await asyncio.sleep(5)  # Attendre avant de réessayer
                        
                        # Si la connexion est perdue, reconnecter
                        if not bot.voice_client or not bot.voice_client.is_connected():
                            bot.voice_client = await channel.connect()
            
            except Exception as e:
                print(f"Erreur lors de la connexion: {e}")
        else:
            print("Salon vocal introuvable.")
    else:
        print("Serveur introuvable.")

def get_uptime():
    """Retourne le temps écoulé depuis le démarrage du bot"""
    if bot.start_time:
        uptime = datetime.datetime.now() - bot.start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}j {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    return "Inconnu"

@bot.event
async def on_ready():
    print(f"{bot.user} est connecté !")
    bot.start_time = datetime.datetime.now()
    
    # Démarrer la lecture de la radio
    bot.loop.create_task(connect_to_channel_and_play())
    
    # Démarrer la tâche de rotation des statuts
    bot.loop.create_task(rotate_status_loop())
    
    # Démarrer la tâche de vérification de connection
    bot.loop.create_task(check_connection_loop())
    
    print("Bot radio démarré avec succès")

async def rotate_status_loop():
    """Change le statut du bot toutes les 30 secondes"""
    while True:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            # Calculer les statistiques
            member_count = guild.member_count
            bot_count = sum(1 for member in guild.members if member.bot)
            human_count = member_count - bot_count
            
            # Liste des statuts possibles
            statuses = [
                f"📻 Radio en direct",
                f"👥 {member_count} membres",
                f"🧑 {human_count} humains",
                f"🤖 {bot_count} bots",
                f"⏱️ En ligne depuis {get_uptime()}"
            ]
            
            # Sélectionner le statut actuel
            status_text = statuses[bot.current_status_index]
            
            # Changer le statut
            activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
            await bot.change_presence(activity=activity)
            
            # Passer au statut suivant
            bot.current_status_index = (bot.current_status_index + 1) % len(statuses)
        
        # Attendre 30 secondes avant de changer à nouveau
        await asyncio.sleep(30)

async def check_connection_loop():
    """Vérifie périodiquement la connexion et la rétablit si nécessaire"""
    while True:
        if not bot.voice_client or not bot.voice_client.is_connected():
            print("Connexion perdue, tentative de reconnexion...")
            bot.loop.create_task(connect_to_channel_and_play())
        await asyncio.sleep(300)  # Vérification toutes les 5 minutes

@bot.event
async def on_voice_state_update(member, before, after):
    """Surveille les changements d'état vocal pour détecter les déconnexions"""
    # Si le bot est déconnecté par quelqu'un
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        print("Bot déconnecté du salon vocal, reconnexion...")
        await asyncio.sleep(3)  # Attendre un peu avant de se reconnecter
        bot.loop.create_task(connect_to_channel_and_play())

# Commande slash /ping
@bot.tree.command(name="ping", description="Vérifier la latence du bot")
async def ping(interaction: discord.Interaction):
    """Répond avec la latence du bot"""
    # Calcul de la latence en millisecondes
    latency = round(bot.latency * 1000)
    
    # Déterminer la qualité de la connexion
    if latency < 100:
        quality = "🟢 Excellente"
    elif latency < 200:
        quality = "🟡 Bonne"
    else:
        quality = "🔴 Lente"
    
    # Créer un embed pour la réponse
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latence du bot: **{latency}ms**\nQualité de connexion: {quality}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(
        name="Informations",
        value=f"• En ligne depuis: **{get_uptime()}**\n• État radio: **{'Connecté' if bot.voice_client and bot.voice_client.is_connected() else 'Déconnecté'}**",
        inline=False
    )
    
    # Ajouter le footer
    embed.set_footer(text=f"Demandé par {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    # Envoyer la réponse
    await interaction.response.send_message(embed=embed)

# Lancer le bot
bot.run(TOKEN)