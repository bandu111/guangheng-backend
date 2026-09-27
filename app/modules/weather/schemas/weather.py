from datetime import datetime

from pydantic import BaseModel, Field


class WeatherLocationSchema(BaseModel):
    location_name: str | None = None
    time_zone: str


class WeatherCurrentSchema(BaseModel):
    time: datetime | None = None
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    relative_humidity_percent: float | None = None
    precipitation_mm: float | None = None
    weather_code: int | None = None
    condition: str
    cloud_cover_percent: float | None = None
    wind_speed_kmh: float | None = None
    is_day: bool | None = None
    shortwave_radiation_w_m2: float | None = None
    direct_normal_irradiance_w_m2: float | None = None


class WeatherHourlySchema(BaseModel):
    time: datetime
    temperature_c: float | None = None
    precipitation_probability_percent: float | None = None
    precipitation_mm: float | None = None
    cloud_cover_percent: float | None = None
    shortwave_radiation_w_m2: float | None = None
    direct_normal_irradiance_w_m2: float | None = None


class WeatherContextSchema(BaseModel):
    available: bool
    provider: str
    location: WeatherLocationSchema | None = None
    current: WeatherCurrentSchema | None = None
    hourly: list[WeatherHourlySchema] = Field(default_factory=list)
    observed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
