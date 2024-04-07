import telebot
from telebot import types
from models import Base, User, Track, engine
from sqlalchemy.orm import sessionmaker
from config import BOT_TOKEN
import logging
from fastkml import kml, geometry
import requests
from math import ceil
from datetime import datetime
from haversine import haversine, Unit


bot = telebot.TeleBot(BOT_TOKEN)
Base.metadata.create_all(engine)

# Создание сессии для работы с базой данных
Session = sessionmaker(bind=engine)
session = Session()


@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user_nickname = message.from_user.username
    user_first_name = message.from_user.first_name
    user_last_name = message.from_user.last_name
    # Проверка, существует ли пользователь в базе данных
    user = session.query(User).filter_by(tg_id=user_id).first()
    if not user:
        # Если пользователь не существует, добавляем его
        new_user = User(tg_id=user_id, nickname=user_nickname, first_name=user_first_name, last_name=user_last_name)
        session.add(new_user)
        session.commit()

    bot.send_message(user_id, 'Привет! Я бот для обмена веломаршрутами. '
                              'Напиши <b>/tracks</b>, чтобы найти новые маршруты', parse_mode='HTML')


@bot.message_handler(commands=['tracks'])
def tracks(message):
    user_id = message.from_user.id
    markup = types.InlineKeyboardMarkup()
    # Кнопочки
    markup.add(types.InlineKeyboardButton('Добавить маршрут', callback_data='add'))
    markup.add(types.InlineKeyboardButton('Посоветуй маршрут', callback_data='view'))
    bot.send_message(user_id, 'Можешь добавить новый маршрут или посмотреть другие!', reply_markup=markup)


class UserState:
    WAITING_FOR_TRACK_NAME = "waiting_for_track_name"
    WAITING_FOR_DIFFICULTY = "waiting_for_difficulty"
    WAITING_FOR_DESCRIPTION = "waiting_for_description"
    WAITING_FOR_1PHOTO = "waiting_for_1photo"
    WAITING_FOR_2PHOTO = "waiting_for_2photo"
    WAITING_FOR_FILE = "waiting_for_file"
    WAITING_FOR_PRIMARY_WIND = "waiting_for_primary_wind"


class PrimaryWind:
    NORD_WIND = "С"
    SOUTH_WIND = "Ю"
    EAST_WIND = "В"
    WEST_WIND = "З"
    NORD_EAST_WIND = "СВ"
    NORD_WEST_WIND = "СЗ"
    SOUTH_EAST_WIND = "ЮВ"
    SOUTH_WEST_WIND = "ЮЗ"


def weather(city):
    api_key = "801be1b4d54c629802744b8d9b2ff85d"
    url = f'http://api.openweathermap.org/data/2.5/forecast?q=Kursk,RU&appid={api_key}'
    response = requests.get(url)
    print(response)
    # Проверяем успешность запроса
    if response.status_code == 200:
        # Данные о погоде в формате JSON
        weather_data = response.json()
        # Выводим данные о погоде
        print(f"Погода в Курске на сегодня: "
              f"{str(datetime.fromtimestamp(weather_data['list'][0]['dt'])).split()[1][:-3]}")
        print(f"Температура: {int(weather_data['list'][0]['main']['temp']) - 273} °C")
        print(f"Атмосферное давление: {weather_data['list'][0]['main']['pressure']} hPa")
        print(f"Влажность: {weather_data['list'][0]['main']['humidity']} %")
        print(f"Осадки: {weather_data['list'][0]['weather'][0]['main']}")
        print(f"Направление ветра: {weather_data['list'][0]['wind']['deg']}°")
        print(f"Скорость ветра: {weather_data['list'][0]['wind']['speed']} м/c")
    else:
        print("Не удалось получить данные о погоде")


@bot.callback_query_handler(func=lambda callback: True)
def add_track(callback):
    user_id = callback.from_user.id
    user = session.query(User).filter_by(tg_id=user_id).first()
    if callback.data == 'add':
        bot.send_message(user_id, 'Хорошо. Введите имя маршрута:')
        session.add(Track(trailholder=user_id))
        track_id = session.query(Track).filter(Track.trailholder == user_id).order_by(Track.id.desc()).first().id
        print(track_id, user.state)
        user.state = UserState.WAITING_FOR_TRACK_NAME
        bot.delete_message(callback.message.chat.id, callback.message.message_id)
        session.commit()
    elif callback.data == 'view':

        bot.delete_message(callback.message.chat.id, callback.message.message_id)
        bot.send_message(user_id, f'Хорошо. Введите имя маршрута: {weather("Курск,RU")}')
    else:
        bot.reply_to(callback, 'Сначала напишите /start, чтобы зарегистрироваться.')


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user = session.query(User).filter_by(tg_id=user_id).first()
    if user:
        track = session.query(Track).filter(Track.trailholder == user_id).order_by(Track.id.desc()).first()
        if user.state == UserState.WAITING_FOR_TRACK_NAME:
            track.name = message.text
            user.state = UserState.WAITING_FOR_DIFFICULTY
            bot.send_message(user_id, 'Введите сложность маршрута (от 0 до 5):')
        elif user.state == UserState.WAITING_FOR_DIFFICULTY:
            difficulty = int(message.text)
            if 0 <= difficulty <= 5:
                track.difficulty = int(message.text)
                user.state = UserState.WAITING_FOR_DESCRIPTION
                bot.send_message(user_id, 'Прикрепите две фотографии к вашему маршруту:')
                user.state = UserState.WAITING_FOR_1PHOTO
            else:
                bot.send_message(user_id, 'Вы ввели неправильное значение!\n'
                                          'Сложность маршрута должна быть от 0 до 5:', parse_mode='HTML')
        elif user.state == UserState.WAITING_FOR_DESCRIPTION:
            track.description = message.text
            bot.send_message(user_id, 'Сбросьте файл маршрута в формате .kml')
            user.state = UserState.WAITING_FOR_FILE
        elif user.state == UserState.WAITING_FOR_PRIMARY_WIND:
            track.primary_wind = message.text
            bot.send_message(user_id, 'Маршрут успешно добавлен!')
            user.state = ' '
        session.commit()
    else:
        bot.reply_to(message, 'Сначала напишите /start, чтобы зарегистрироваться.')


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    user = session.query(User).filter_by(tg_id=user_id).first()
    if user:
        # Находим маршрут который в данный момент создаёт пользователь и загружаем фотографии, которые он отправил
        track = session.query(Track).filter(Track.trailholder == user_id).order_by(Track.id.desc()).first()
        file_info = bot.get_file(message.photo[-1].file_id)
        file_content = bot.download_file(file_info.file_path)
        if user.state == UserState.WAITING_FOR_1PHOTO:
            track.photo1 = file_content
            user.state = UserState.WAITING_FOR_2PHOTO
        elif user.state == UserState.WAITING_FOR_2PHOTO:
            track.photo2 = file_content
            session.commit()
            user.state = UserState.WAITING_FOR_DESCRIPTION
            bot.send_message(user_id, 'Опишите свой маршрут в паре предложений:')


@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    user = session.query(User).filter_by(tg_id=user_id).first()
    if user and user.state == UserState.WAITING_FOR_FILE:
        # Получаем файл
        file_info = bot.get_file(message.document.file_id)
        file_content = bot.download_file(file_info.file_path)
        # Находим последний добавленный трек этого пользователя
        track = session.query(Track).filter(Track.trailholder == user_id).order_by(Track.id.desc()).first()
        # Читаем прикреплённый .kml файл и находим координаты маршрута
        track.file = file_content
        k = kml.KML()
        k.from_string(file_content)
        coordinates = []
        distance = 0.0
        for doc in k.features():
            for folder in doc.features():
                for placemark in folder.features():
                    if isinstance(placemark.geometry, geometry.LineString):
                        for coord in placemark.geometry.coords:
                            lon, lat, *_ = coord
                            coordinates.append(coord)
        # Считаем длину маршрута
        for coord in range(len(coordinates) - 1):
            point1 = (coordinates[coord][1], coordinates[coord][0])
            point2 = (coordinates[coord + 1][1], coordinates[coord + 1][0])
            distance += haversine(point1, point2, unit=Unit.KILOMETERS)
        track.distance = int(ceil(distance))
        session.commit()
        bot.send_message(user_id, 'Укажите направление ветра, которое лучше всего подходит к вашему маршруту.\n'
                                  'Если ветер Юго-Восточный (то есть дует с Юго-Востока), то напишите "<b>ЮВ</b>"',
                         parse_mode='HTML')
        user.state = UserState.WAITING_FOR_PRIMARY_WIND
    else:
        bot.reply_to(message, 'Сначала напишите <b>/tracks</b>, чтобы добавить маршрут.', parse_mode='HTML')


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
bot.infinity_polling()
