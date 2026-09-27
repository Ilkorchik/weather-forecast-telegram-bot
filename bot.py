import os
import httpx

from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from timezonefinder import TimezoneFinder

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

# MET Norway требует идентифицировать приложение
USER_AGENT = "WeatherForecastTelegramBot/1.0"

# Определение часового пояса по координатам
timezone_finder = TimezoneFinder()

# Кэш городов
city_cache = {}

# Кэш прогнозов
weather_cache = {}


# =========================================================
# ПОИСК ГОРОДА
# =========================================================

async def get_city(city_name):

    cache_key = city_name.lower().strip()

    if cache_key in city_cache:
        return city_cache[cache_key]

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": city_name,
        "format": "jsonv2",
        "limit": 1,
        "accept-language": "ru",
    }

    headers = {
        "User-Agent": USER_AGENT
    }

    async with httpx.AsyncClient() as client:

        response = await client.get(
            url,
            params=params,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

    if not data:
        return None

    result = data[0]

    latitude = float(result["lat"])
    longitude = float(result["lon"])

    # Определяем часовой пояс
    timezone_name = timezone_finder.timezone_at(
        lat=latitude,
        lng=longitude
    )

    if timezone_name is None:
        timezone_name = "UTC"

    # Получаем название страны
    address = result.get("display_name", "")
    parts = [
        part.strip()
        for part in address.split(",")
    ]

    country = parts[-1] if parts else ""

    city = {
        "name": city_name,
        "country": country,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone_name,
    }

    city_cache[cache_key] = city

    return city


# =========================================================
# ПОЛУЧЕНИЕ ПРОГНОЗА MET NORWAY
# =========================================================

async def get_weather(latitude, longitude):

    cache_key = (
        round(latitude, 4),
        round(longitude, 4)
    )

    # Если прогноз уже загружали —
    # используем его повторно
    if cache_key in weather_cache:

        saved_time, weather = weather_cache[cache_key]

        # Кэш действует 30 минут
        if (
            datetime.now().timestamp()
            - saved_time
            < 1800
        ):
            print(
                "Используем прогноз из кэша"
            )

            return weather

    url = (
        "https://api.met.no/"
        "weatherapi/locationforecast/2.0/complete"
    )

    params = {
        "lat": round(latitude, 4),
        "lon": round(longitude, 4),
    }

    headers = {
        "User-Agent": USER_AGENT
    }

    async with httpx.AsyncClient() as client:

        response = await client.get(
            url,
            params=params,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        weather = response.json()

    weather_cache[cache_key] = (
        datetime.now().timestamp(),
        weather
    )

    return weather


# =========================================================
# ПРЕОБРАЗОВАНИЕ КОДА ПОГОДЫ MET NORWAY
# =========================================================

def weather_description(symbol):

    symbol = symbol.lower()

    descriptions = {

        "clearsky": "☀️ Ясно",

        "fair": "🌤 Преимущественно ясно",

        "partlycloudy": "⛅ Переменная облачность",

        "cloudy": "☁️ Пасмурно",

        "fog": "🌫 Туман",

        "lightrain": "🌦 Небольшой дождь",
        "rain": "🌧 Дождь",
        "heavyrain": "🌧 Сильный дождь",

        "lightrainshowers": "🌦 Небольшой ливень",
        "rainshowers": "🌧 Ливень",
        "heavyrainshowers": "🌧 Сильный ливень",

        "lightsleet": "🌨 Небольшой мокрый снег",
        "sleet": "🌨 Мокрый снег",
        "heavysleet": "🌨 Сильный мокрый снег",

        "lightsleetshowers": "🌨 Небольшой мокрый снег",
        "sleetshowers": "🌨 Мокрый снег",
        "heavysleetshowers": "🌨 Сильный мокрый снег",

        "lightsnow": "🌨 Небольшой снег",
        "snow": "🌨 Снег",
        "heavysnow": "❄️ Сильный снег",

        "lightsnowshowers": "🌨 Небольшой снег",
        "snowshowers": "🌨 Снег",
        "heavysnowshowers": "❄️ Сильный снег",

        "lightrainshowersandthunder": "⛈ Ливень с грозой",
        "rainshowersandthunder": "⛈ Ливень с грозой",
        "heavyrainshowersandthunder": "⛈ Сильный ливень с грозой",

        "lightrainandthunder": "⛈ Дождь с грозой",
        "rainandthunder": "⛈ Дождь с грозой",
        "heavyrainandthunder": "⛈ Сильный дождь с грозой",

        "lightsnowshowersandthunder": "⛈ Снег с грозой",
        "snowshowersandthunder": "⛈ Снег с грозой",
        "heavysnowshowersandthunder": "⛈ Сильный снег с грозой",

        "lightsnowandthunder": "⛈ Снег с грозой",
        "snowandthunder": "⛈ Снег с грозой",
        "heavysnowandthunder": "⛈ Сильный снег с грозой",
    }

    for key, description in descriptions.items():

        if symbol.startswith(key):
            return description

    return "🌡 Неизвестная погода"


# =========================================================
# ВРЕМЯ
# =========================================================

def local_datetime(time_string, timezone_name):

    dt = datetime.fromisoformat(
        time_string.replace("Z", "+00:00")
    )

    timezone = ZoneInfo(timezone_name)

    return dt.astimezone(timezone)


def format_time(time_string, timezone_name):

    try:

        dt = local_datetime(
            time_string,
            timezone_name
        )

        return dt.strftime("%H:%M")

    except Exception:

        return time_string


# =========================================================
# ПОЛУЧЕНИЕ ДАННЫХ ЗА ПЕРИОД
# =========================================================

def get_period_data(
    weather,
    timezone_name,
    start_hour,
    end_hour
):

    timeseries = weather[
        "properties"
    ]["timeseries"]

    temperatures = []
    feels = []
    humidity = []
    precipitation = []
    wind = []
    gusts = []
    symbols = []

    for item in timeseries:

        dt = local_datetime(
            item["time"],
            timezone_name
        )

        hour = dt.hour

        if not (
            start_hour <= hour < end_hour
        ):
            continue

        instant = item[
            "data"
        ].get("instant", {}).get("details", {})

        temperature = instant.get(
            "air_temperature"
        )

        humidity_value = instant.get(
            "relative_humidity"
        )

        wind_speed = instant.get(
            "wind_speed"
        )

        gust = instant.get(
            "wind_speed_of_gust"
        )

        if temperature is None:
            continue

        temperatures.append(
            temperature
        )

        # MET Norway не отдаёт отдельную
        # apparent_temperature как Open-Meteo,
        # поэтому пока используем температуру
        # как базовое значение ощущения.
        feels.append(
            temperature
        )

        if humidity_value is not None:
            humidity.append(
                humidity_value
            )

        if wind_speed is not None:
            wind.append(
                wind_speed
            )

        if gust is not None:
            gusts.append(
                gust
            )

        # Берём вероятность осадков
        # и погодный символ
        period_data = item[
            "data"
        ].get("next_1_hours")

        if period_data is None:
            period_data = item[
                "data"
            ].get("next_6_hours")

        if period_data:

            details = period_data.get(
                "details",
                {}
            )

            rain_probability = details.get(
                "probability_of_precipitation"
            )

            if rain_probability is not None:
                precipitation.append(
                    rain_probability
                )

            symbol = period_data.get(
                "summary",
                {}
            ).get(
                "symbol_code"
            )

            if symbol:
                symbols.append(symbol)

    if not temperatures:
        return None

    if symbols:

        most_common_symbol = max(
            set(symbols),
            key=symbols.count
        )

    else:

        most_common_symbol = "clearsky"

    return {

        "min_temp": min(temperatures),
        "max_temp": max(temperatures),

        "min_feels": min(feels),
        "max_feels": max(feels),

        "humidity": (
            sum(humidity) / len(humidity)
            if humidity
            else 0
        ),

        "precipitation": (
            max(precipitation)
            if precipitation
            else 0
        ),

        "wind": (
            sum(wind) / len(wind)
            if wind
            else 0
        ),

        "gust": (
            max(gusts)
            if gusts
            else 0
        ),

        "symbol": most_common_symbol,
    }


# =========================================================
# ОПИСАНИЕ ПЕРИОДА
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

        f"{weather_description(data['symbol'])}\n"

        f"💨 "
        f"{data['wind']:.1f} м/с"
        f", порывы до "
        f"{data['gust']:.1f} м/с\n"

        f"💧 "
        f"{data['humidity']:.0f}%\n"

        f"🌧 Осадки: "
        f"{data['precipitation']:.0f}%\n"
    )


# =========================================================
# СОЗДАНИЕ ПРОГНОЗА НА СЕГОДНЯ
# =========================================================

def create_forecast(city, weather):

    timezone_name = city["timezone"]

    timeseries = weather[
        "properties"
    ]["timeseries"]

    today = datetime.now(
        ZoneInfo(timezone_name)
    ).date()

    today_items = []

    for item in timeseries:

        dt = local_datetime(
            item["time"],
            timezone_name
        )

        if dt.date() == today:

            today_items.append(item)

    if not today_items:
        raise Exception(
            "Нет данных за сегодняшний день"
        )

    temperatures = []

    for item in today_items:

        temperature = item[
            "data"
        ]["instant"]["details"].get(
            "air_temperature"
        )

        if temperature is not None:
            temperatures.append(
                temperature
            )

    min_temp = min(temperatures)
    max_temp = max(temperatures)

    night = get_period_data(
        weather,
        timezone_name,
        0,
        6
    )

    morning = get_period_data(
        weather,
        timezone_name,
        6,
        12
    )

    day = get_period_data(
        weather,
        timezone_name,
        12,
        18
    )

    evening = get_period_data(
        weather,
        timezone_name,
        18,
        24
    )

    text = (

        "🌤 <b>ПРОГНОЗ НА СЕГОДНЯ</b>\n\n"

        f"📍 <b>{city['name']}</b>, "
        f"{city['country']}\n\n"

        f"🌡 Температура за день: "
        f"<b>{min_temp:+.0f}..."
        f"{max_temp:+.0f}°C</b>\n\n"

        "────────────────────\n\n"
    )

    text += format_period(
        "🌙 НОЧЬ",
        night
    )

    text += "\n────────────────────\n\n"

    text += format_period(
        "🌅 УТРО",
        morning
    )

    text += "\n────────────────────\n\n"

    text += format_period(
        "☀️ ДЕНЬ",
        day
    )

    text += "\n────────────────────\n\n"

    text += format_period(
        "🌆 ВЕЧЕР",
        evening
    )

    text += (

        "\n────────────────────\n\n"

        "🌐 Данные: MET Norway / "
        "OpenStreetMap"
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

        print(
            f"Ищу город: {city_name}"
        )

        city = await get_city(
            city_name
        )

        if city is None:

            await update.message.reply_text(

                "❌ <b>Город не найден.</b>\n\n"

                "Попробуй написать название "
                "по-другому.",

                parse_mode="HTML"
            )

            return

        print(
            f"Город найден: "
            f"{city['name']} "
            f"({city['latitude']}, "
            f"{city['longitude']})"
        )

        weather = await get_weather(
            city["latitude"],
            city["longitude"]
        )

        print(
            "Прогноз получен от MET Norway"
        )

        forecast = create_forecast(
            city,
            weather
        )

        context.user_data["city"] = city
        context.user_data["weather"] = weather

        await update.message.reply_text(

            forecast,

            parse_mode="HTML",

            reply_markup=create_buttons()
        )

    except Exception as error:

        print(
            "Ошибка:",
            repr(error)
        )

        await update.message.reply_text(

            "⚠️ <b>Не удалось получить "
            "прогноз.</b>\n\n"

            "Попробуй ещё раз.",

            parse_mode="HTML"
        )


# =========================================================
# КНОПКИ
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

    city = context.user_data.get(
        "city"
    )

    weather = context.user_data.get(
        "weather"
    )

    if not city or not weather:
        return

    # Сегодня
    if query.data == "today":

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

        timezone_name = city["timezone"]

        timeseries = weather[
            "properties"
        ]["timeseries"]

        days = {}

        for item in timeseries:

            dt = local_datetime(
                item["time"],
                timezone_name
            )

            date = dt.date()

            if date not in days:
                days[date] = []

            days[date].append(item)

        text = (
            "📆 <b>ПРОГНОЗ НА 7 ДНЕЙ</b>\n\n"
            f"📍 <b>{city['name']}</b>\n\n"
        )

        for date in sorted(days)[:7]:

            items = days[date]

            temperatures = []
            symbols = []
            rain = []

            for item in items:

                details = item[
                    "data"
                ]["instant"]["details"]

                temperature = details.get(
                    "air_temperature"
                )

                if temperature is not None:
                    temperatures.append(
                        temperature
                    )

                period = item[
                    "data"
                ].get("next_6_hours")

                if period:

                    period_details = period.get(
                        "details",
                        {}
                    )

                    probability = (
                        period_details.get(
                            "probability_of_precipitation"
                        )
                    )

                    if probability is not None:
                        rain.append(
                            probability
                        )

                    symbol = period.get(
                        "summary",
                        {}
                    ).get(
                        "symbol_code"
                    )

                    if symbol:
                        symbols.append(symbol)

            if not temperatures:
                continue

            min_temp = min(
                temperatures
            )

            max_temp = max(
                temperatures
            )

            if symbols:

                symbol = max(
                    set(symbols),
                    key=symbols.count
                )

            else:

                symbol = "clearsky"

            rain_probability = (
                max(rain)
                if rain
                else 0
            )

            text += (

                f"<b>{date}</b>\n"

                f"{weather_description(symbol)}\n"

                f"🌡 "
                f"{min_temp:+.0f}..."
                f"{max_temp:+.0f}°C\n"

                f"🌧 Осадки: "
                f"{rain_probability:.0f}%\n\n"
            )

        text += (
            "🌐 Данные: MET Norway / "
            "OpenStreetMap"
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
        "🐡 Weather bot запущен!"
    )

    render_url = os.environ.get(
        "RENDER_EXTERNAL_URL"
    )

    if render_url:

        port = int(
            os.environ.get(
                "PORT",
                10000
            )
        )

        application.run_webhook(

            listen="0.0.0.0",

            port=port,

            url_path=BOT_TOKEN,

            webhook_url=(
                f"{render_url}/{BOT_TOKEN}"
            ),

            drop_pending_updates=True,
        )

    else:

        application.run_polling()


if __name__ == "__main__":
    main()