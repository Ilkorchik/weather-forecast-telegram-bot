import os
import httpx

from datetime import datetime

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


# =========================================================
# ПОИСК ГОРОДА
# =========================================================

async def get_city(city_name):

    url = "https://geocoding-api.open-meteo.com/v1/search"

    params = {
        "name": city_name,
        "count": 1,
        "language": "ru",
        "format": "json",
    }

    async with httpx.AsyncClient() as client:

        response = await client.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

    if "results" not in data:
        return None

    result = data["results"][0]

    return {
        "name": result["name"],
        "country": result.get("country", ""),
        "latitude": result["latitude"],
        "longitude": result["longitude"],
    }


# =========================================================
# ПОЛУЧЕНИЕ ПРОГНОЗА
# =========================================================

async def get_weather(latitude, longitude):

    url = "https://api.open-meteo.com/v1/forecast"

    params = {

        "latitude": latitude,
        "longitude": longitude,

        "hourly": (
            "temperature_2m,"
            "apparent_temperature,"
            "relative_humidity_2m,"
            "precipitation_probability,"
            "weather_code,"
            "wind_speed_10m,"
            "wind_gusts_10m,"
            "wind_direction_10m"
        ),

        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "weather_code,"
            "precipitation_probability_max,"
            "sunrise,"
            "sunset"
        ),

        "timezone": "auto",

        "forecast_days": 7,
    }

    async with httpx.AsyncClient() as client:

        response = await client.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        return response.json()


# =========================================================
# ОПИСАНИЕ ПОГОДЫ
# =========================================================

def weather_description(code):

    descriptions = {

        0: "☀️ Ясно",

        1: "🌤 Преимущественно ясно",
        2: "⛅ Переменная облачность",
        3: "☁️ Пасмурно",

        45: "🌫 Туман",
        48: "🌫 Туман",

        51: "🌦 Лёгкая морось",
        53: "🌦 Морось",
        55: "🌧 Сильная морось",

        61: "🌧 Небольшой дождь",
        63: "🌧 Дождь",
        65: "🌧 Сильный дождь",

        71: "🌨 Небольшой снег",
        73: "🌨 Снег",
        75: "❄️ Сильный снег",

        80: "🌦 Небольшой ливень",
        81: "🌧 Ливень",
        82: "🌧 Сильный ливень",

        95: "⛈ Гроза",
        96: "⛈ Гроза с градом",
        99: "⛈ Сильная гроза с градом",
    }

    return descriptions.get(
        code,
        "🌡 Неизвестная погода"
    )


# =========================================================
# ФОРМАТИРОВАНИЕ ВРЕМЕНИ
# =========================================================

def format_time(time_string):

    try:

        dt = datetime.fromisoformat(time_string)

        return dt.strftime("%H:%M")

    except:

        return time_string


# =========================================================
# ПОЛУЧЕНИЕ ДАННЫХ ЗА ПЕРИОД
# =========================================================

def get_period_data(
    weather,
    start_hour,
    end_hour
):

    hourly = weather["hourly"]

    temperatures = []
    feels = []
    humidity = []
    precipitation = []
    wind = []
    gusts = []
    codes = []

    for i, time_string in enumerate(hourly["time"]):

        hour = int(
            time_string.split("T")[1][:2]
        )

        if start_hour <= hour < end_hour:

            temperatures.append(
                hourly["temperature_2m"][i]
            )

            feels.append(
                hourly["apparent_temperature"][i]
            )

            humidity.append(
                hourly["relative_humidity_2m"][i]
            )

            precipitation.append(
                hourly["precipitation_probability"][i]
            )

            wind.append(
                hourly["wind_speed_10m"][i]
            )

            gusts.append(
                hourly["wind_gusts_10m"][i]
            )

            codes.append(
                hourly["weather_code"][i]
            )

    if not temperatures:
        return None

    # Наиболее частый погодный код
    most_common_code = max(
        set(codes),
        key=codes.count
    )

    return {

        "min_temp": min(temperatures),
        "max_temp": max(temperatures),

        "min_feels": min(feels),
        "max_feels": max(feels),

        "humidity": sum(humidity) / len(humidity),

        "precipitation": max(precipitation),

        "wind": sum(wind) / len(wind),

        "gust": max(gusts),

        "code": most_common_code,
    }


# =========================================================
# ОПИСАНИЕ ОДНОГО ПЕРИОДА
# =========================================================

def format_period(
    title,
    data
):

    if data is None:
        return ""

    return (

        f"<b>{title}</b>\n"

        f"🌡 "
        f"{data['min_temp']:+.0f}..."
        f"{data['max_temp']:+.0f}°C\n"

        f"🥶 Ощущается: "
        f"{data['min_feels']:+.0f}..."
        f"{data['max_feels']:+.0f}°C\n"

        f"{weather_description(data['code'])}\n"

        f"💨 "
        f"{data['wind']:.1f} м/с"
        f", порывы до "
        f"{data['gust']:.1f} м/с\n"

        f"💧 "
        f"{data['humidity']:.0f}%\n"

        f"🌧 Осадки: "
        f"{data['precipitation']}%\n"
    )


# =========================================================
# СОЗДАНИЕ ПРОГНОЗА
# =========================================================

def create_forecast(city, weather):

    daily = weather["daily"]

    today = daily["time"][0]

    min_temp = daily["temperature_2m_min"][0]
    max_temp = daily["temperature_2m_max"][0]

    sunrise = format_time(
        daily["sunrise"][0]
    )

    sunset = format_time(
        daily["sunset"][0]
    )

    precipitation = daily[
        "precipitation_probability_max"
    ][0]

    text = (

        f"🌤 <b>ПРОГНОЗ НА СЕГОДНЯ</b>\n\n"

        f"📍 <b>{city['name']}</b>, "
        f"{city['country']}\n"

        f"📅 {today}\n\n"

        f"🌡 Температура за день: "
        f"<b>{min_temp:+.0f}..."
        f"{max_temp:+.0f}°C</b>\n"

        f"🌧 Максимальная вероятность "
        f"осадков: <b>{precipitation}%</b>\n\n"

        f"────────────────────\n\n"
    )

    # Ночь
    night = get_period_data(
        weather,
        0,
        6
    )

    text += format_period(
        "🌙 НОЧЬ",
        night
    )

    text += "\n────────────────────\n\n"

    # Утро
    morning = get_period_data(
        weather,
        6,
        12
    )

    text += format_period(
        "🌅 УТРО",
        morning
    )

    text += "\n────────────────────\n\n"

    # День
    day = get_period_data(
        weather,
        12,
        18
    )

    text += format_period(
        "☀️ ДЕНЬ",
        day
    )

    text += "\n────────────────────\n\n"

    # Вечер
    evening = get_period_data(
        weather,
        18,
        24
    )

    text += format_period(
        "🌆 ВЕЧЕР",
        evening
    )

    text += (

        "\n────────────────────\n\n"

        f"🌅 Восход: <b>{sunrise}</b>\n"
        f"🌇 Закат: <b>{sunset}</b>\n\n"

        "🌐 Данные: Open-Meteo"
    )

    return text


# =========================================================
# КНОПКИ
# =========================================================

def create_buttons():

    keyboard = [

        [
            InlineKeyboardButton(
                "📅 Сегодня",
                callback_data="today"
            ),

            InlineKeyboardButton(
                "📆 7 дней",
                callback_data="week"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔄 Другой город",
                callback_data="new_city"
            )
        ],

    ]

    return InlineKeyboardMarkup(
        keyboard
    )


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "👋 <b>Привет!</b>\n\n"

        "🌤 Я бот прогноза погоды.\n\n"

        "Напиши название города, "
        "и я покажу подробный прогноз.\n\n"

        "Например:\n"
        "📍 Краснодар\n"
        "📍 Москва\n"
        "📍 Берлин\n"
        "📍 Санкт-Петербург",

        parse_mode="HTML"
    )


# =========================================================
# ПОЛУЧЕНИЕ ГОРОДА
# =========================================================

async def city_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    city_name = update.message.text.strip()

    if not city_name:
        return

    await update.message.reply_text(
        f"🔎 Ищу прогноз для "
        f"<b>{city_name}</b>...",
        parse_mode="HTML"
    )

    try:

        # Ищем город
        city = await get_city(city_name)

        if city is None:

            await update.message.reply_text(

                "❌ <b>Город не найден.</b>\n\n"

                "Попробуй написать название "
                "по-другому.",

                parse_mode="HTML"
            )

            return

        # Получаем погоду
        weather = await get_weather(
            city["latitude"],
            city["longitude"]
        )

        # Создаём прогноз
        forecast = create_forecast(
            city,
            weather
        )

        # Сохраняем данные
        context.user_data["city"] = city
        context.user_data["weather"] = weather

        # Отправляем
        await update.message.reply_text(

            forecast,

            parse_mode="HTML",

            reply_markup=create_buttons()
        )

    except Exception as error:

        print(
            "Ошибка:",
            error
        )

        await update.message.reply_text(

            "⚠️ <b>Не удалось получить "
            "прогноз.</b>\n\n"
            "Попробуй ещё раз.",

            parse_mode="HTML"
        )


# =========================================================
# ОБРАБОТКА КНОПОК
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    # Другой город
    if query.data == "new_city":

        await query.message.reply_text(

            "📍 Напиши название нового города."
        )

        return

    # Сегодня
    if query.data == "today":

        city = context.user_data.get(
            "city"
        )

        weather = context.user_data.get(
            "weather"
        )

        if city and weather:

            forecast = create_forecast(
                city,
                weather
            )

            await query.message.reply_text(

                forecast,

                parse_mode="HTML",

                reply_markup=create_buttons()
            )

        return

    # 7 дней
    if query.data == "week":

        city = context.user_data.get(
            "city"
        )

        weather = context.user_data.get(
            "weather"
        )

        if not city or not weather:
            return

        daily = weather["daily"]

        text = (

            f"📆 <b>ПРОГНОЗ НА 7 ДНЕЙ</b>\n\n"

            f"📍 <b>{city['name']}</b>\n\n"
        )

        for i in range(7):

            date = daily["time"][i]

            min_temp = daily[
                "temperature_2m_min"
            ][i]

            max_temp = daily[
                "temperature_2m_max"
            ][i]

            code = daily[
                "weather_code"
            ][i]

            rain = daily[
                "precipitation_probability_max"
            ][i]

            text += (

                f"<b>{date}</b>\n"

                f"{weather_description(code)}\n"

                f"🌡 "
                f"{min_temp:+.0f}..."
                f"{max_temp:+.0f}°C\n"

                f"🌧 Осадки: {rain}%\n\n"
            )

        await query.message.reply_text(

            text,

            parse_mode="HTML",

            reply_markup=create_buttons()
        )


# =========================================================
# ЗАПУСК
# =========================================================

def main():

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            city_message
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    print(
        "🌤 Weather bot запущен!"
    )

    application.run_polling()


if __name__ == "__main__":
    main()