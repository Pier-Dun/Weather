import asyncio
import time
import aiosqlite
import httpx
import uvicorn
from fastapi import FastAPI


app = FastAPI(title='Погода')
db_name = 'Weather.db'


async def db_init():
    async with aiosqlite.connect(db_name) as db:
        await db.execute(
            '''CREATE TABLE IF NOT EXISTS Cities(
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                latitude REAL,
                longitude REAL
            );'''
        )
        await db.execute(
            '''CREATE TABLE IF NOT EXISTS Weather(
                id INTEGER PRIMARY KEY,
                temperature REAL,
                pressure REAL,
                wind REAL,
                lastUpdate DATETIME
            );'''
        )
        await db.commit()

async def get_weather_info(url):
    async with httpx.AsyncClient() as ahtx:
        return await ahtx.get(url)

async def update_weather_current_city(city_id: int):
    async with aiosqlite.connect(db_name) as db:
        async with db.execute(f'SELECT * FROM Cities WHERE id = {city_id}') as cursor:
            city = await cursor.fetchone()
            result = await get_weather(city[2], city[3])
            print(city[1], str(result['current']['time']).replace('T', ' '))
            await db.execute('UPDATE Weather ' +
                             f'SET temperature = {result['current']['temperature_2m']}, ' +
                             f'pressure = {result['current']['surface_pressure'] * 75 / 100}, ' +
                             f'wind = {result['current']['wind_speed_10m']}, ' +
                             f'lastUpdate = \'{str(result['current']['time']).replace('T', ' ')}\' ' +
                             f'WHERE id = {city[0]}')
            await db.commit()

async def update_weather():
    async with aiosqlite.connect(db_name) as db:
        async with db.execute('SELECT id FROM Cities') as cursor:
            all_cities_id = await cursor.fetchall()
            tasks = []
            for city_id in all_cities_id:
                task = asyncio.create_task(update_weather_current_city(city_id[0]))
                tasks.append(task)
            await asyncio.gather(*tasks)

async def update_weather_every15m():
    while True:
        start = time.time()
        await update_weather()
        end = time.time() - start
        print(round(end, 2))
        await asyncio.sleep(15*60)



@app.on_event("startup")
async def startup():
    await db_init()
    update = asyncio.create_task(update_weather_every15m())
    update

@app.get('/get_weather')
async def get_weather(lat: float, lon: float):
    answer = await get_weather_info(f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,rain,surface_pressure,wind_speed_10m&timezone=auto')
    return answer.json()

@app.get('/get_weather_hourly')
async def get_weather_hourly(lat: float, lon: float):
    answer = await get_weather_info(f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,rain,surface_pressure,wind_speed_10m&timezone=auto&forecast_days=1')
    return answer.json()

@app.post('/add_city')
async def add_city(city_name: str, lat: float, lon: float):
    async with aiosqlite.connect(db_name) as db:
        try:
            await db.execute('INSERT INTO Cities (name, latitude, longitude) VALUES (?, ?, ?)', (city_name, lat, lon))
            await db.commit()
        except aiosqlite.IntegrityError:
            return {"error": "City already exists"}
        async with db.execute('SELECT * FROM Cities') as cursor:
            info = await cursor.fetchall()
            await db.execute('INSERT INTO Weather (id) VALUES (?)', (info[-1][0],))
            await db.commit()
            await update_weather_current_city(info[-1][0])
    return {'success': True, 'message': f'Город {city_name} c координатами {lat} {lon} успешно добавлен'}

@app.get('/delete_city')
async def delete_city(city_name: str):
    print(city_name)
    async with aiosqlite.connect(db_name) as db:
        async with db.execute(f'SELECT * FROM Cities WHERE name = \'{city_name}\'') as c:
            c = await c.fetchone()
            await db.execute(f'DELETE FROM Weather WHERE id = \'{c[0]}\'')
            await db.execute(f'DELETE FROM Cities WHERE name = \'{city_name}\'')
            await db.commit()
    return {'success': True, 'message': f'Город {city_name} успешно удален'}

@app.get('/get_cities')
async def get_cities():
    async with aiosqlite.connect(db_name) as db:
        c = await db.execute('SELECT * FROM Cities')
        list_of_cities = await c.fetchall()
    return list_of_cities

@app.get('/get_weather_of_city')
async def get_weather_of_city(city_name: str):
    async with aiosqlite.connect(db_name) as db:
        async with db.execute(f'SELECT latitude, longitude FROM Cities WHERE name = \'{city_name}\'') as c:
            lat_lon = await c.fetchone()
            city_info = await get_weather_hourly(lat_lon[0], lat_lon[1])
    return city_info


if __name__ == '__main__':
    uvicorn.run(app)
