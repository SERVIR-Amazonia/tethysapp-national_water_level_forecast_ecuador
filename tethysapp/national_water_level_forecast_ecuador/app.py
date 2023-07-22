from tethys_sdk.base import TethysAppBase


class NationalWaterLevelForecastEcuador(TethysAppBase):
    """
    Tethys app class for National Water Level Forecast Ecuador.
    """

    name = 'National Water Level Forecast Ecuador'
    description = ''
    package = 'national_water_level_forecast_ecuador'  # WARNING: Do not change this value
    index = 'home'
    icon = f'{package}/images/icon.gif'
    root_url = 'national-water-level-forecast-ecuador'
    color = '#20295c'
    tags = ''
    enable_feedback = False
    feedback_emails = []