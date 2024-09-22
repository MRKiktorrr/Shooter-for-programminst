import socket
import threading
import json
import pygame
import math
import time


# Настройки клиента
SERVER_HOST = '5.42.87.198'  # Измените на IP сервера
SERVER_PORT = 21491

PLAYER_RADIUS = 20
# Инициализация Pygame
pygame.init()
WIDTH, HEIGHT = 800, 600  # Исходный размер окна
win = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Сетевая игра")
clock = pygame.time.Clock()

# Цвета
COLOR_MAP = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0)
}

# Игровые объекты
players = {}
walls = []
bullets = []
player_id = None
hp = 5
score = 0
time_left = 120
last_shot = 0
window_width = WIDTH
window_height = HEIGHT

# Сетевое соединение
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    client.connect((SERVER_HOST, SERVER_PORT))
except:
    print("Не удалось подключиться к серверу.")
    exit()

# Получение начальных данных
buffer = ""
while True:
    data = client.recv(4096).decode()
    if not data:
        print("Сервер закрыл соединение.")
        exit()
    buffer += data
    if "\n" in buffer:
        message, buffer = buffer.split("\n", 1)
        if not message:
            continue
        init_data = json.loads(message)
        if init_data["type"] == "init":
            player_id = init_data["player_id"]
            players = {int(k): v for k, v in init_data["players"].items()}
            walls = init_data["walls"]
            time_left = init_data["game_duration"]
            window_width = init_data.get("window_width", WIDTH)
            window_height = init_data.get("window_height", HEIGHT)
            # Изменяем размер окна в соответствии с сервером
            if window_width != WIDTH or window_height != HEIGHT:
                win = pygame.display.set_mode((window_width, window_height))
                WIDTH, HEIGHT = window_width, window_height
            break
        elif init_data["type"] == "full":
            print("Сервер переполнен.")
            exit()

# Функция получения обновлений от сервера
def receive():
    global players, walls, bullets, time_left, window_width, window_height
    buffer = ""
    while True:
        try:
            data = client.recv(4096).decode()
            if not data:
                print("Сервер закрыл соединение.")
                break
            buffer += data
            while "\n" in buffer:
                message, buffer = buffer.split("\n", 1)
                if not message:
                    continue
                data = json.loads(message)
                if data["type"] == "update":
                    players = {int(k): v for k, v in data["players"].items()}
                    walls = data["walls"]
                    bullets = data["bullets"]
                    time_left = data["time_left"]
                    window_width = data.get("window_width", window_width)
                    window_height = data.get("window_height", window_height)
        except:
            break



threading.Thread(target=receive, daemon=True).start()

# Основной игровой цикл
running = True
while running:
    clock.tick(60)
    win.fill((0, 0, 0))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Управление игроком
    keys = pygame.key.get_pressed()
    dx, dy = 0, 0
    speed = 5  # Исходная скорость
    if keys[pygame.K_w]:
        dy -= speed
    if keys[pygame.K_s]:
        dy += speed
    if keys[pygame.K_a]:
        dx -= speed
    if keys[pygame.K_d]:
        dx += speed
    if dx != 0 or dy != 0:
        move_data = {"type": "move", "dx": dx, "dy": dy}
        try:
            client.sendall((json.dumps(move_data) + "\n").encode())
        except:
            pass

    # Обработка стрельбы (нажатие левой кнопки мыши)
    mouse_pressed = pygame.mouse.get_pressed()
    if mouse_pressed[0] and time.time() - last_shot > 1 and players.get(player_id, {}).get("alive", False):
        mouse_x, mouse_y = pygame.mouse.get_pos()
        player = players.get(player_id, {})
        if player:
            dir_x = mouse_x - player["x"]
            dir_y = mouse_y - player["y"]
            length = math.hypot(dir_x, dir_y)
            if length != 0:
                dir_x /= length
                dir_y /= length
                shoot_data = {"type": "shoot", "dir_x": dir_x, "dir_y": dir_y}
                try:
                    client.sendall((json.dumps(shoot_data) + "\n").encode())
                    last_shot = time.time()
                except:
                    pass
    
    
    # Рендер стен
    for wall in walls:
        pygame.draw.rect(win, (100, 100, 100), (wall["x"], wall["y"], wall["size"], wall["size"]))

    # Рендер пуль
    for bullet in bullets:
        pygame.draw.circle(win, (255, 255, 255), (int(bullet["x"]), int(bullet["y"])), 5)

    # Рендер игроков
    for pid, p in players.items():
        if p["alive"]:
            pygame.draw.circle(win, COLOR_MAP.get(p["color"], (255, 255, 255)), (int(p["x"]), int(p["y"])), PLAYER_RADIUS)
        else:
            # Отображение мертвого игрока как серый круг
            pygame.draw.circle(win, (50, 50, 50), (int(p["x"]), int(p["y"])), PLAYER_RADIUS)
        # Отображение HP
        font = pygame.font.SysFont(None, 24)
        hp_text = font.render(f'HP: {p["hp"]}', True, (255, 255, 255))
        win.blit(hp_text, (p["x"] - PLAYER_RADIUS, p["y"] - PLAYER_RADIUS - 20))
        # Отображение имени/ID игрока
        id_text = font.render(f'Player {pid}', True, (255, 255, 255))
        win.blit(id_text, (p["x"] - PLAYER_RADIUS, p["y"] + PLAYER_RADIUS + 5))

    # Отображение счета и времени
    font = pygame.font.SysFont(None, 36)
    my_score = players.get(player_id, {}).get("score", 0)
    score_text = font.render(f'Score: {my_score}', True, (255, 255, 255))
    time_text = font.render(f'Time Left: {time_left}', True, (255, 255, 255))
    win.blit(score_text, (10, 10))
    win.blit(time_text, (10, 50))

    pygame.display.flip()



pygame.quit()
client.close()

