from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash
import os, random, string
from dotenv import load_dotenv
from datetime import datetime, timedelta


load_dotenv()

# ---------- Supabase ----------
SUPABASE_URL = os.getenv("SUPA_URL")
SUPABASE_KEY = os.getenv("SUPA_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = "myappsecret"


@app.route('/')
def index():
    return redirect(url_for('home'))

@app.route('/home')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template("home.html")

# =========================================
#               API
# =========================================
@app.route('/api/lobby/<code>')
def api_lobby(code):
    lobby = supabase.table("lobbies").select("*").eq("code", code).execute()

    if not lobby.data:
        return jsonify({
            "status": "closed",
            "redirect": "/dashboard"
        }), 200   # ⚠ НЕ 404

    players = supabase.table("lobby_players")\
        .select("nickname")\
        .eq("lobby_code", code)\
        .execute()

    return jsonify({
        "status": "ok",
        "host": lobby.data[0]["host"],
        "players": [p["nickname"] for p in players.data]
    })

@app.route('/api/lobby_status/<code>')
def lobby_status(code):
    """Check if a game has started for this lobby"""
    game = supabase.table("games").select("*").eq("lobby_code", code).execute()
    if game.data:
        return {"started": True, "game_code": game.data[0]["game_code"]}
    return {"started": False}

# =========================================
#               REGISTER
# =========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        password = request.form.get('password')

        if not nickname or not password:
            flash("Заповніть усі поля!", "error")
            return redirect(url_for("register"))

        existing = supabase.table("users").select("id").eq("nickname", nickname).execute()
        if existing.data:
            flash("Нікнейм вже використовується!", "error")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        supabase.table("users").insert({
            "nickname": nickname,
            "password": hashed_password
        }).execute()

        flash("Реєстрація успішна!", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# =========================================
#                 LOGIN
# =========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        password = request.form.get('password')

        user = supabase.table("users").select("*").eq("nickname", nickname).execute()

        if user.data and check_password_hash(user.data[0]['password'], password):
            session['user'] = nickname
            flash("Успішний вхід!", "success")
            return redirect(url_for("dashboard"))

        flash("Невірний нікнейм або пароль!", "error")
        return redirect(url_for("login"))

    return render_template("login.html")

# =========================================
#               DASHBOARD
# =========================================
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        flash("Спочатку увійдіть!", "error")
        return redirect(url_for("login"))

    lobbies = supabase.table("lobbies").select("*").order("created_at", desc=True).execute()

    quotes = [
        "“Кожен бос починав із малого — головне не здатися.”",
        "“У мафії немає друзів — лише союзники.”",
        "“Сім’я — усе. Решта — просто бізнес.”",
        "“Кодекс честі простий: поважай сильного, пам'ятай слабкого.”"
    ]

    return render_template(
        "dashboard.html",
        lobbies=lobbies.data,
        user=session['user'],
        quote=random.choice(quotes)
    )

# =========================================
#               LOBBY MENU
# =========================================
@app.route('/lobby')
def lobby():
    if 'user' not in session:
        flash("Спочатку увійдіть!", "error")
        return redirect(url_for('login'))
    return render_template("lobby.html")

# =========================================
#              CREATE LOBBY
# =========================================
@app.route('/create_lobby', methods=['POST'])
def create_lobby():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']

    # remove user from other lobbies
    supabase.table("lobby_players").delete().eq("nickname", user).execute()

    # delete lobby if user is host
    old_lobby = supabase.table("lobbies").select("code").eq("host", user).execute()
    if old_lobby.data:
        supabase.table("lobbies").delete().eq("code", old_lobby.data[0]["code"]).execute()

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

    supabase.table("lobbies").insert({
        "code": code,
        "host": user
    }).execute()

    supabase.table("lobby_players").insert({
        "lobby_code": code,
        "nickname": user
    }).execute()

    session["lobby_code"] = code
    flash(f"Лоббі створено! Код: {code}", "success")
    return redirect(url_for("lobby_room", code=code))

# =========================================
#               JOIN LOBBY
# =========================================
@app.route('/join_lobby', methods=['POST'])
def join_lobby():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    code = request.form.get('code', '').upper()

    lobby = supabase.table("lobbies").select("*").eq("code", code).execute()
    if not lobby.data:
        flash("Лоббі не знайдено!", "error")
        return redirect(url_for('lobby'))

    supabase.table("lobby_players").delete().eq("nickname", user).execute()

    supabase.table("lobby_players").insert({
        "lobby_code": code,
        "nickname": user
    }).execute()

    session["lobby_code"] = code
    flash(f"Ви приєдналися до лоббі {code}", "success")
    return redirect(url_for("lobby_room", code=code))

# =========================================
#               LOBBY ROOM
# =========================================
@app.route('/lobby/<code>')
def lobby_room(code):
    if 'user' not in session:
        return redirect(url_for("login"))

    lobby = supabase.table("lobbies").select("*").eq("code", code).execute()
    if not lobby.data:
        flash("Лоббі не існує!", "error")
        return redirect(url_for("dashboard"))

    players = supabase.table("lobby_players") \
        .select("nickname") \
        .eq("lobby_code", code) \
        .execute()

    return render_template(
        "lobby_room.html",
        code=code,
        host=lobby.data[0]["host"],
        players=[p["nickname"] for p in players.data],
        user=session["user"]
    )

@app.route('/leave_lobby/<code>', methods=['POST'])
def leave_lobby(code):
    if 'user' not in session:
        return redirect(url_for("login"))

    user = session['user']

    # Fetch the lobby
    lobby = supabase.table("lobbies").select("*").eq("code", code).execute()
    if not lobby.data:
        flash("Лоббі не знайдено!", "error")
        return redirect(url_for("dashboard"))

    # Check if user is host
    if lobby.data[0]["host"] == user:
        # Host leaves → delete entire lobby and all players
        supabase.table("lobby_players").delete().eq("lobby_code", code).execute()
        supabase.table("lobbies").delete().eq("code", code).execute()
        flash("Ви закрили лоббі.", "info")
    else:
        # Regular player leaves → just remove from lobby_players
        supabase.table("lobby_players").delete().eq("nickname", user).execute()
        flash("Ви покинули лоббі.", "info")

    # Clear lobby_code from session
    session.pop("lobby_code", None)
    return redirect(url_for("dashboard"))

@app.route('/game/<game_code>')
def game_room(game_code):
    if 'user' not in session:
        return redirect(url_for("login"))

    # Check if game exists
    game = supabase.table("games").select("*").eq("game_code", game_code).execute()
    if not game.data:
        flash("Гра не знайдена!", "error")
        return redirect(url_for("dashboard"))

    # Check if player is part of this game
    player = supabase.table("game_players").select("*").eq("game_code", game_code).eq("nickname", session['user']).execute()
    if not player.data:
        flash("Ви не граєте в цій грі!", "error")
        return redirect(url_for("dashboard"))

    return render_template("game_room.html", game_code=game_code)


# ---------- /start_game/<code> route ----------

@app.route('/start_game/<code>', methods=['POST'])
def start_game(code):
    if 'user' not in session:
        return redirect(url_for("login"))

    user = session['user']
    lobby = supabase.table("lobbies").select("*").eq("code", code).execute()
    if not lobby.data:
        flash("Лоббі не знайдено!", "error")
        return redirect(url_for("dashboard"))

    if lobby.data[0]["host"] != user:
        flash("Тільки хост може почати гру!", "error")
        return redirect(url_for("lobby_room", code=code))

    # Отримати гравців
    players_data = supabase.table("lobby_players").select("nickname").eq("lobby_code", code).execute()
    players = [p["nickname"] for p in players_data.data]
    player_count = len(players)

    if player_count < 4:
        flash("Мінімум 4 гравці потрібно для початку гри!", "error")
        return redirect(url_for("lobby_room", code=code))

    # Ролі
    roles = []
    if player_count == 4:
        roles = ["mafia", "civilian", "civilian", random.choice(["commisar", "commisar"])]
    elif player_count == 5:
        roles = ["mafia", "civilian", "civilian", "civilian", random.choice(["commisar", "surgeon"])]
    elif player_count == 6:
        roles = ["don", "mafia", "civilian", "civilian", "commisar", "surgeon"]
    elif player_count == 7:
        roles = ["mafia", "don", "civilian", "civilian", "commisar", "surgeon", "homeless"]

    random.shuffle(roles)

    game_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    now = datetime.now()
    phase_duration = timedelta(seconds=35)

    # Створюємо гру: стартуємо з night
    supabase.table("games").insert({
        "game_code": game_code,
        "lobby_code": code,
        "phase": "night",
        "phase_start": now.isoformat(),
        "phase_end": (now + phase_duration).isoformat(),
        "is_active": True
    }).execute()

    # Створюємо гравців
    for i, player in enumerate(players):
        supabase.table("game_players").insert({
            "game_code": game_code,
            "nickname": player,
            "role": roles[i],
            "alive": True
        }).execute()

    session["game_code"] = game_code
    flash("Гра почалася!", "success")
    return redirect(url_for("game_room", game_code=game_code))

# ---------- Game phase route ----------
@app.route('/api/game_phase/<game_code>')
def game_phase(game_code):
    game_res = supabase.table("games").select("*").eq("game_code", game_code).execute()
    if not game_res.data:
        return {"error": "Гра не знайдена"}, 404

    game = game_res.data[0]
    now = datetime.now()
    phase_end = datetime.fromisoformat(game["phase_end"])

    # Якщо таймер закінчився або всі живі гравці зробили дію
    alive_players = supabase.table("game_players").select("*").eq("game_code", game_code).eq("alive", True).execute().data
    actions = supabase.table("game_actions").select("*").eq("game_code", game_code).eq("phase", game["phase"]).execute().data

    phase_finished = (now >= phase_end) or (len(actions) >= len(alive_players))

    if phase_finished:
        # Якщо ніч → застосовуємо дії
        if game["phase"] == "night":
            mafia_target = None
            heal_target = None

            for a in actions:
                if a["action_type"] in ["kill", "vote_kill"]:
                    mafia_target = a["target"]
                elif a["action_type"] == "heal":
                    heal_target = a["target"]

            if mafia_target and mafia_target != heal_target:
                supabase.table("game_players").update({"alive": False}).eq("game_code", game_code).eq("nickname", mafia_target).execute()

        # Якщо день → застосовуємо голосування
        if game["phase"] == "day":
            votes = {}
            for a in actions:
                if a["action_type"] == "vote":
                    votes[a["target"]] = votes.get(a["target"], 0) + 1
            if votes:
                max_votes = max(votes.values())
                # гравці з максимальною кількістю голосів
                kicked = [p for p, v in votes.items() if v == max_votes]
                if len(kicked) == 1:  # лише один гравець вилітає
                    supabase.table("game_players").update({"alive": False}).eq("game_code", game_code).eq("nickname", kicked[0]).execute()

        # Переключаємо фазу
        new_phase = "day" if game["phase"] == "night" else "night"
        duration = timedelta(seconds=35)
        supabase.table("games").update({
            "phase": new_phase,
            "phase_start": now.isoformat(),
            "phase_end": (now + duration).isoformat()
        }).eq("game_code", game_code).execute()

        # Видаляємо всі дії минулої фази
        supabase.table("game_actions").delete().eq("game_code", game_code).eq("phase", game["phase"]).execute()

        game["phase"] = new_phase
        game["phase_start"] = now.isoformat()
        game["phase_end"] = (now + duration).isoformat()

    return {
        "phase": game["phase"],
        "phase_start": game["phase_start"],
        "phase_end": game["phase_end"]
    }


@app.route('/api/game/<game_code>')
def api_game(game_code):
    game = supabase.table("games").select("*").eq("game_code", game_code).execute()

    if not game.data or not game.data[0]["is_active"]:
        return jsonify({
            "status": "ended",
            "redirect": "/dashboard"
        }), 200

    players = supabase.table("game_players")\
        .select("*")\
        .eq("game_code", game_code)\
        .execute()

    return jsonify({
        "status": "ok",
        "players": players.data
    })


@app.route("/api/night_action", methods=["POST"])
def night_action():
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    data = request.json
    game_code = data["game_code"]
    target = data["target"]
    role = data["role"]
    actor = session["user"]

    # Validate role
    allowed = ["mafia", "don", "commisar", "surgeon", "homeless"]
    if role not in allowed:
        return {"error": "Invalid role"}, 400

    # One action per night
    supabase.table("game_actions").delete() \
        .eq("game_code", game_code) \
        .eq("actor", actor) \
        .execute()

    supabase.table("game_actions").insert({
        "game_code": game_code,
        "actor": actor,
        "target": target,
        "role": role
    }).execute()

    return {"status": "ok"}


@app.route("/api/vote", methods=["POST"])
def vote():
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    data = request.json
    game_code = data["game_code"]
    target = data["target"]
    voter = session["user"]

    # Check alive
    alive = supabase.table("game_players") \
        .select("alive") \
        .eq("game_code", game_code) \
        .eq("nickname", voter) \
        .execute()

    if not alive.data or not alive.data[0]["alive"]:
        return {"error": "Dead players can't vote"}, 403

    # Upsert vote (1 vote per player)
    supabase.table("game_votes").delete() \
        .eq("game_code", game_code) \
        .eq("voter", voter) \
        .execute()

    supabase.table("game_votes").insert({
        "game_code": game_code,
        "voter": voter,
        "target": target
    }).execute()

    return {"status": "ok"}

# ---------- Game action route ----------
@app.route('/api/game_actions/<game_code>', methods=['POST'])
def game_actions(game_code):
    if 'user' not in session:
        return {"error": "Not logged in"}, 403

    data = request.json
    actor = session['user']
    action_type = data.get('action_type')
    target = data.get('target')
    phase = data.get('phase')

    # Перевіряємо чи гравець ще живий
    player = supabase.table("game_players").select("*") \
        .eq("game_code", game_code).eq("nickname", actor).execute()
    if not player.data or not player.data[0]['alive']:
        return {"error": "You are dead"}, 403

    # Додаємо дію
    supabase.table("game_actions").insert({
        "game_code": game_code,
        "phase": phase,
        "actor": actor,
        "action_type": action_type,
        "target": target
    }).execute()

    return {"status": "ok"}


# ---------- GET game actions/results ----------
@app.route('/api/game_results/<game_code>')
def game_results(game_code):
    game = supabase.table("games").select("*").eq("game_code", game_code).execute()
    if not game.data:
        return {"error": "Game not found"}, 404

    phase = game.data[0]['phase']

    actions = supabase.table("game_actions") \
        .select("*").eq("game_code", game_code).eq("phase", phase).execute()

    # Для кожного гравця можна показати лише результат дії
    events = []
    for a in actions.data:
        if a['action_type'] in ['kill', 'vote', 'shoot']:
            events.append(f"Хтось зробив дію: {a['action_type']}")  # без ніка
        elif a['action_type'] == 'heal':
            events.append(f"Хтось вилікував гравця")
        elif a['action_type'] == 'check':
            events.append(f"Хтось перевірив роль гравця")
    return {"events": events, "phase": phase}


@app.route('/logout')
def logout():
    session.clear()
    flash("Ви вийшли з акаунту.", "info")
    return redirect(url_for("home"))

if __name__ == '__main__':
    app.run(debug=True)
