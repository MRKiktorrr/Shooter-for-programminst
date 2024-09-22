import socket
import threading
import json
import random
import time
import math

# Настройки сервера
HOST = '0.0.0.0'  # Слушать все доступные интерфейсы
PORT = 21491
MAX_PLAYERS = 4
GAME_DURATION = 120  # 2 минуты
RESPAWN_TIME = 5
NUM_WALLS = 20  # Количество стен, можно изменить по желанию

# Игровые данные
players = {}
walls = []
bullets = []
colors = ["red", "green", "blue", "yellow"]
spawn_points = [
    {"x": 50, "y": 50},
    {"x": 750, "y": 50},
    {"x": 50, "y": 550},
    {"x": 750, "y": 550}
]
lock = threading.Lock()

# Размеры окна
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

# Радиус игрока
PLAYER_RADIUS = 20

# Размер стен
WALL_SIZE = 50  # Сделаем размер стен одинаковым (квадраты)

# Максимальное количество рикошетов
MAX_BOUNCES = 5

def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))

def circle_rect_collision(circle_x, circle_y, circle_radius, rect_x, rect_y, rect_size):
    # Найти ближайшую точку к окружности внутри прямоугольника
    closest_x = clamp(circle_x, rect_x, rect_x + rect_size)
    closest_y = clamp(circle_y, rect_y, rect_y + rect_size)

    # Вычислить расстояние между окружностью и ближайшей точкой
    distance_x = circle_x - closest_x
    distance_y = circle_y - closest_y

    distance_squared = distance_x**2 + distance_y**2

    return distance_squared < circle_radius**2

def generate_walls():
    walls = []
    for _ in range(NUM_WALLS):
        size = WALL_SIZE  # Размер квадрата
        x = random.randint(0, WINDOW_WIDTH - size)
        y = random.randint(0, WINDOW_HEIGHT - size)
        walls.append({"x": x, "y": y, "size": size})
    return walls

def send_data(conn, data):
    try:
        conn.sendall((json.dumps(data) + "\n").encode())
    except:
        pass  # Игнорировать ошибки отправки

def handle_client(conn, addr, player_id):
    global players, bullets
    print(f"Новое подключение: {addr}")

    # Инициализация игрока
    spawn = spawn_points[player_id % len(spawn_points)]
    with lock:
        players[player_id] = {
            "id": player_id,
            "x": spawn["x"],
            "y": spawn["y"],
            "color": colors[player_id % len(colors)],
            "hp": 5,
            "score": 0,
            "respawn_timer": 0,
            "alive": True
        }

    # Отправка начальных данных
    init_data = {
        "type": "init",
        "player_id": player_id,
        "players": players,
        "walls": walls,
        "game_duration": GAME_DURATION,
        "window_width": WINDOW_WIDTH,
        "window_height": WINDOW_HEIGHT
    }
    send_data(conn, init_data)

    try:
        buffer = ""
        while True:
            data = conn.recv(1024).decode()
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                message, buffer = buffer.split("\n", 1)
                if not message:
                    continue
                data = json.loads(message)
                with lock:
                    if data["type"] == "move" and players[player_id]["alive"]:
                        # Предварительный расчет новой позиции
                        new_x = players[player_id]["x"] + data.get("dx", 0)
                        new_y = players[player_id]["y"] + data.get("dy", 0)

                        collision = False
                        for wall in walls:
                            if circle_rect_collision(new_x, new_y, PLAYER_RADIUS, wall["x"], wall["y"], wall["size"]):
                                collision = True
                                break

                        if not collision:
                            # Ограничение позиции игрока в границах окна
                            players[player_id]["x"] = clamp(new_x, PLAYER_RADIUS, WINDOW_WIDTH - PLAYER_RADIUS)
                            players[player_id]["y"] = clamp(new_y, PLAYER_RADIUS, WINDOW_HEIGHT - PLAYER_RADIUS)
                    elif data["type"] == "shoot" and players[player_id]["alive"]:
                        bullet = {
                            "x": players[player_id]["x"],
                            "y": players[player_id]["y"],
                            "dir_x": data["dir_x"],
                            "dir_y": data["dir_y"],
                            "owner": player_id,
                            "bounces": 0
                        }
                        bullets.append(bullet)
    except:
        pass
    finally:
        with lock:
            del players[player_id]
        conn.close()
        print(f"Отключился: {addr}")

def reflect_bullet(bullet, wall):
    # Определение стороны столкновения
    # Предполагается, что стены оси-ориентированные
    # Проверяем направление движения пули

    # Центры пули и стены
    bullet_prev_x = bullet["x"] - bullet["dir_x"] * 10
    bullet_prev_y = bullet["y"] - bullet["dir_y"] * 10

    wall_x = wall["x"]
    wall_y = wall["y"]
    wall_size = wall["size"]

    # Проверяем, была ли пуля слева или справа от стены до столкновения
    if bullet_prev_x < wall_x and bullet["x"] >= wall_x:
        # Столкновение с левой стороной стены
        bullet["dir_x"] = -bullet["dir_x"]
    elif bullet_prev_x > wall_x + wall_size and bullet["x"] <= wall_x + wall_size:
        # Столкновение с правой стороной стены
        bullet["dir_x"] = -bullet["dir_x"]

    # Проверяем, была ли пуля сверху или снизу стены до столкновения
    if bullet_prev_y < wall_y and bullet["y"] >= wall_y:
        # Столкновение с верхней стороной стены
        bullet["dir_y"] = -bullet["dir_y"]
    elif bullet_prev_y > wall_y + wall_size and bullet["y"] <= wall_y + wall_size:
        # Столкновение с нижней стороной стены
        bullet["dir_y"] = -bullet["dir_y"]

def server_loop():
    global walls, bullets
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"Сервер запущен на {HOST}:{PORT}")

    walls = generate_walls()
    player_id = 0

    # Таймер игры
    start_time = time.time()

    # Список подключенных клиентов
    clients = {}

    # Поток для принятия новых подключений
    def accept_connections():
        nonlocal player_id
        while True:
            conn, addr = server.accept()
            with lock:
                if len(players) >= MAX_PLAYERS:
                    send_data(conn, {"type": "full"})
                    conn.close()
                    continue
                current_id = player_id
                player_id += 1
                clients[current_id] = conn
            threading.Thread(target=handle_client, args=(conn, addr, current_id), daemon=True).start()

    threading.Thread(target=accept_connections, daemon=True).start()

    # Главный игровой цикл
    while True:
        current_time = time.time()
        elapsed = current_time - start_time

        with lock:
            # Обновление таймеров респавна
            for p in players.values():
                if not p["alive"]:
                    p["respawn_timer"] -= 1/60
                    if p["respawn_timer"] <= 0:
                        spawn = spawn_points[p["id"] % len(spawn_points)]
                        # Проверяем, нет ли стены на спавне
                        collision = False
                        for wall in walls:
                            if circle_rect_collision(spawn["x"], spawn["y"], PLAYER_RADIUS, wall["x"], wall["y"], wall["size"]):
                                collision = True
                                break
                        if not collision:
                            p["x"] = spawn["x"]
                            p["y"] = spawn["y"]
                            p["hp"] = 5
                            p["alive"] = True

            # Обновление позиций пуль
            for bullet in bullets[:]:
                bullet["x"] += bullet["dir_x"] * 10
                bullet["y"] += bullet["dir_y"] * 10

                # Проверка выхода за границы и реализация рикошета от границ
                if bullet["x"] < 0 or bullet["x"] > WINDOW_WIDTH or bullet["y"] < 0 or bullet["y"] > WINDOW_HEIGHT:
                    if bullet["x"] < 0 or bullet["x"] > WINDOW_WIDTH:
                        bullet["dir_x"] = -bullet["dir_x"]
                    if bullet["y"] < 0 or bullet["y"] > WINDOW_HEIGHT:
                        bullet["dir_y"] = -bullet["dir_y"]
                    bullet["bounces"] += 1
                    if bullet["bounces"] > MAX_BOUNCES:
                        bullets.remove(bullet)
                        continue
                    else:
                        # Ограничиваем пули внутри границ
                        bullet["x"] = clamp(bullet["x"], 0, WINDOW_WIDTH)
                        bullet["y"] = clamp(bullet["y"], 0, WINDOW_HEIGHT)

                # Проверка столкновений со стенами
                collided = False
                for wall in walls:
                    if (wall["x"] <= bullet["x"] <= wall["x"] + wall["size"] and
                        wall["y"] <= bullet["y"] <= wall["y"] + wall["size"]):
                        if bullet["bounces"] < MAX_BOUNCES:
                            reflect_bullet(bullet, wall)
                            bullet["bounces"] += 1
                        else:
                            bullets.remove(bullet)
                        collided = True
                        break
                if collided:
                    continue

                # Проверка столкновений с игроками
                for pid, p in players.items():
                    if pid != bullet["owner"] and p["alive"]:
                        distance = math.hypot(p["x"] - bullet["x"], p["y"] - bullet["y"])
                        if distance < PLAYER_RADIUS:
                            p["hp"] -= 1
                            if p["hp"] <= 0:
                                p["alive"] = False
                                p["respawn_timer"] = RESPAWN_TIME
                                players[bullet["owner"]]["score"] += 1
                            if bullet in bullets:
                                bullets.remove(bullet)
                            break

            # Проверка окончания игры
            if elapsed > GAME_DURATION:
                # Сброс игры
                walls = generate_walls()
                bullets.clear()
                for p in players.values():
                    p["hp"] = 5
                    p["score"] = 0
                    p["alive"] = True
                start_time = current_time

            # Подготовка данных для отправки
            game_data = {
                "type": "update",
                "players": players,
                "walls": walls,
                "bullets": bullets,
                "time_left": max(0, GAME_DURATION - int(elapsed)),
                "window_width": WINDOW_WIDTH,
                "window_height": WINDOW_HEIGHT
            }

            # Отправка данных всем клиентам
            disconnected_players = []
            for pid, conn in clients.items():
                try:
                    send_data(conn, game_data)
                except:
                    disconnected_players.append(pid)

            # Удаление отключившихся клиентов
            for pid in disconnected_players:
                del clients[pid]
                if pid in players:
                    del players[pid]

        time.sleep(1/60)  # 60 обновлений в секунду

if __name__ == "__main__":
    server_loop()