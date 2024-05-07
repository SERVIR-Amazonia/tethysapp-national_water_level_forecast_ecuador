####################################################################################################
##                                   LIBRARIES AND DEPENDENCIES                                   ##
####################################################################################################

# Tethys platform
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from tethys_sdk.routing import controller
from tethys_sdk.gizmos import PlotlyView
import hydrostats.data as hd

# Postgresql
import io
import psycopg2
import pandas as pd
from sqlalchemy import create_engine
from pandas_geojson import to_geojson

# App settings
from .app import NationalWaterLevelForecastEcuador as app

# App models
from .models.data import *
from .models.plots import *



####################################################################################################
##                                       STATUS VARIABLES                                         ##
####################################################################################################

# Import enviromental variables 
DB_USER = app.get_custom_setting('DB_USER')
DB_PASS = app.get_custom_setting('DB_PASS')
DB_NAME = app.get_custom_setting('DB_NAME')
APP_NAME = "national_water_level_forecast_ecuador"
APP_URL = APP_NAME.replace("_", "-")

# Generate the conection token
tokencon = "postgresql+psycopg2://{0}:{1}@localhost:5432/{2}".format(DB_USER, DB_PASS, DB_NAME)




####################################################################################################
##                                   CONTROLLERS AND REST APIs                                    ##
####################################################################################################
@controller(name='home', url=APP_URL)
def home(request):
    context = {
        "server": app.get_custom_setting('SERVER'),
        "app_name": APP_NAME
    }
    return render(request, '{0}/home.html'.format(APP_NAME), context)



@controller(name='get_stations',url='{0}/get-stations'.format(APP_URL))
def get_stations(request):
    # Establish connection to database
    db= create_engine(tokencon)
    conn = db.connect()
    # Query to database
    stations = pd.read_sql("select *, concat(code, ' - ', left(name, 23)) from waterlevel_station", conn);
    conn.close()
    stations = to_geojson(
        df = stations,
        lat = "latitude",
        lon = "longitude",
        properties = ["basin", "code", "name", "latitude", "longitude", "elevation", "comid", "river", 
                      "loc1", "loc2", "loc3", "alert", "concat"]
    )
    return JsonResponse(stations)


# Return streamflow station (in geojson format) 
@controller(name='get_data',url='{0}/get-data'.format(APP_URL))
def get_data(request):
    # Retrieving GET arguments
    station_code = request.GET['codigo']
    station_comid = request.GET['comid']
    station_name = request.GET['nombre']
    plot_width = float(request.GET['width']) - 12
    plot_width_2 = 0.5*plot_width

    # Establish connection to database
    db= create_engine(tokencon)
    conn = db.connect()

    # Data series
    observed_data = get_format_data("select datetime, {0} from waterlevel_data order by datetime;".format(station_code), conn)
    simulated_data = get_format_data("select * from r_{0} where datetime < '2022-06-01 00:00:00';".format(station_comid), conn)
    corrected_data = get_bias_corrected_data(simulated_data, observed_data)

    # Raw forecast
    ensemble_forecast = get_format_data("select * from f_{0};".format(station_comid), conn)
    forecast_records = get_format_data("select * from fr_{0};".format(station_comid), conn)
    return_periods = get_return_periods(station_comid, simulated_data)

    # Corrected forecast
    corrected_ensemble_forecast = get_corrected_forecast(simulated_data, ensemble_forecast, observed_data)
    corrected_forecast_records = get_corrected_forecast_records(forecast_records, simulated_data, observed_data)
    corrected_return_periods = get_return_periods(station_comid, corrected_data)

    # Stats for raw and corrected forecast
    ensemble_stats = get_ensemble_stats(ensemble_forecast)
    corrected_ensemble_stats = get_ensemble_stats(corrected_ensemble_forecast)

    # Merge data (For plots)
    global merged_sim
    merged_sim = hd.merge_data(sim_df = simulated_data, obs_df = observed_data)
    global merged_cor
    merged_cor = hd.merge_data(sim_df = corrected_data, obs_df = observed_data)

    # Close conection
    conn.close()

    # Historical data plot
    corrected_data_plot = get_historic_simulation(
        cor = corrected_data, 
        obs = observed_data, 
        code = station_code,
        name = station_name)
    
    # Daily averages plot
    daily_average_plot = get_daily_average_plot(
        cor = merged_cor,
        sim = merged_sim,
        code = station_code,
        name = station_name)   
    
    # Monthly averages plot
    monthly_average_plot = get_monthly_average_plot(
        cor = merged_cor,
        sim = merged_sim,
        code = station_code,
        name = station_name) 
    
    # Scatter plot
    data_scatter_plot = get_scatter_plot(
        cor = merged_cor,
        sim = merged_sim,
        code = station_code,
        name = station_name,
        log = False) 
    
    # Scatter plot (Log scale)
    log_data_scatter_plot = get_scatter_plot(
        cor = merged_cor,
        sim = merged_sim,
        code = station_code,
        name = station_name,
        log = True) 
    
    # Metrics table
    metrics_table = get_metrics_table(
        cor = merged_cor,
        sim = merged_sim,
        my_metrics = ["ME", "RMSE", "NRMSE (Mean)", "NSE", "KGE (2009)", "KGE (2012)", "R (Pearson)", "R (Spearman)", "r2"]) 
    
    # Percent of Ensembles that Exceed Return Periods    
    corrected_forecast_table = get_probabilities_table(
        stats = corrected_ensemble_stats,
        ensem = corrected_ensemble_forecast, 
        rperiods = corrected_return_periods)

    # Ensemble forecast plot    
    corrected_ensemble_forecast_plot = get_forecast_stats(
            stats = corrected_ensemble_stats, 
            rperiods = corrected_return_periods, 
            records = corrected_forecast_records, 
            sim = corrected_data, 
            code = station_code, 
            name = station_name)
    
    #returning
    context = {
        "corrected_data_plot": PlotlyView(corrected_data_plot.update_layout(width = plot_width)),
        "daily_average_plot": PlotlyView(daily_average_plot.update_layout(width = plot_width)),
        "monthly_average_plot": PlotlyView(monthly_average_plot.update_layout(width = plot_width)),
        "data_scatter_plot": PlotlyView(data_scatter_plot.update_layout(width = plot_width_2)),
        "log_data_scatter_plot": PlotlyView(log_data_scatter_plot.update_layout(width = plot_width_2)),
        "corrected_ensemble_forecast_plot": PlotlyView(corrected_ensemble_forecast_plot.update_layout(width = plot_width)),
        "metrics_table": metrics_table,
        "corrected_forecast_table": corrected_forecast_table,
    }
    return render(request, 'national_water_level_forecast_ecuador/panel.html', context)



@controller(name='get_metrics_custom',url='{0}/get-metrics-custom'.format(APP_URL))
def get_metrics_custom(request):
    # Combine metrics
    my_metrics_1 = ["ME", "RMSE", "NRMSE (Mean)", "NSE", "KGE (2009)", "KGE (2012)", "R (Pearson)", "R (Spearman)", "r2"]
    my_metrics_2 = request.GET['metrics'].split(",")
    lista_combinada = my_metrics_1 + my_metrics_2
    elementos_unicos = []
    elementos_vistos = set()
    for elemento in lista_combinada:
        if elemento not in elementos_vistos:
            elementos_unicos.append(elemento)
            elementos_vistos.add(elemento)
    # Compute metrics
    metrics_table = get_metrics_table(
        cor = merged_cor,
        sim = merged_sim,
        my_metrics = elementos_unicos)
    return HttpResponse(metrics_table)


@controller(name='get_raw_forecast_date',url='{0}/get-raw-forecast-date'.format(APP_URL))
def get_raw_forecast_date(request):
    ## Variables
    station_code = request.GET['codigo']
    station_comid = request.GET['comid']
    station_name = request.GET['nombre']
    forecast_date = request.GET['fecha']
    plot_width = float(request.GET['width']) - 12

    # Establish connection to database
    db= create_engine(tokencon)
    conn = db.connect()

    # Data series
    observed_data = get_format_data("select datetime, {0} from waterlevel_data order by datetime;".format(station_code), conn)
    simulated_data = get_format_data("select * from r_{0} where datetime < '2022-06-01 00:00:00';".format(station_comid), conn)
    corrected_data = get_bias_corrected_data(simulated_data, observed_data)
    
    # Raw forecast
    ensemble_forecast = get_forecast_date(station_comid, forecast_date)
    forecast_records = get_forecast_record_date(station_comid, forecast_date)
    return_periods = get_return_periods(station_comid, simulated_data)

    # Corrected forecast
    corrected_ensemble_forecast = get_corrected_forecast(simulated_data, ensemble_forecast, observed_data)
    corrected_forecast_records = get_corrected_forecast_records(forecast_records, simulated_data, observed_data)
    corrected_return_periods = get_return_periods(station_comid, corrected_data)
    
    # Forecast stats
    ensemble_stats = get_ensemble_stats(ensemble_forecast)
    corrected_ensemble_stats = get_ensemble_stats(corrected_ensemble_forecast)

    # Close conection
    conn.close()

    # Plotting corrected forecast
    corr_ensemble_forecast_plot = get_forecast_stats(
        stats = corrected_ensemble_stats, 
        rperiods = corrected_return_periods, 
        records = corrected_forecast_records, 
        sim = corrected_data, 
        code = station_code, 
        name = station_name).update_layout(width = plot_width).to_html()
    
    # Corrected forecast table
    corr_forecast_table = get_probabilities_table(
        stats = corrected_ensemble_stats,
        ensem = corrected_ensemble_forecast, 
        rperiods = corrected_return_periods)
    
    return JsonResponse({
       'corr_ensemble_forecast_plot': corr_ensemble_forecast_plot,
       'corr_forecast_table': corr_forecast_table
    })
    

@controller(name='get_drainage_json', url='{0}/get-drainage-json'.format(APP_URL))
def get_drainage_json(request):
    # Reemplaza 'URL_DEL_GEOJSON' con la URL real de tu archivo GeoJSON
    url_geojson = 'https://geoserver.hydroshare.org/geoserver/HS-77951ba9bcf04ac5bc68ae3be2acfd90/wfs?service=WFS&version=1.0.0&request=GetFeature&typeName=ecuador-geoglows-drainage&outputFormat=application/json'
    try:
        # Descargar el GeoJSON desde la URL
        response = requests.get(url_geojson)
        response.raise_for_status()  # Verificar si la solicitud fue exitosa
        geojson_data = response.json()  # Convertir la respuesta a JSON
        # Devolver el GeoJSON como respuesta JSON
        return JsonResponse(geojson_data, safe=False)
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Error al obtener el GeoJSON: {str(e)}'}, status=500)


@controller(name='get_ffgs_json', url='{0}/get-ffgs-json'.format(APP_URL))
def get_ffgs_json(request):
    # Reemplaza 'URL_DEL_GEOJSON' con la URL real de tu archivo GeoJSON
    url_geojson = 'https://geoserver.hydroshare.org/geoserver/HS-352379cf82444fd099eca8bfc662789b/wfs?service=WFS&version=1.0.0&request=GetFeature&typeName=nwsaffds&maxFeatures=20000&outputFormat=application/json'
    try:
        # Descargar el GeoJSON desde la URL
        response = requests.get(url_geojson)
        response.raise_for_status()  # Verificar si la solicitud fue exitosa
        geojson_data = response.json()  # Convertir la respuesta a JSON
        # Devolver el GeoJSON como respuesta JSON
        return JsonResponse(geojson_data, safe=False)
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Error al obtener el GeoJSON: {str(e)}'}, status=500)


@controller(name='get_warnings_json', url='{0}/get-warnings-json'.format(APP_URL))
def get_warnings_json(request):
    # Reemplaza 'URL_DEL_GEOJSON' con la URL real de tu archivo GeoJSON
    url_geojson = 'https://geoserver.hydroshare.org/geoserver/HS-e1920951d6194c78948e45ae7b08ec64/wfs?service=WFS&version=1.0.0&request=GetFeature&typeName=Advertencia&outputFormat=application/json'
    try:
        # Descargar el GeoJSON desde la URL
        response = requests.get(url_geojson)
        response.raise_for_status()  # Verificar si la solicitud fue exitosa
        geojson_data = response.json()  # Convertir la respuesta a JSON
        # Devolver el GeoJSON como respuesta JSON
        return JsonResponse(geojson_data, safe=False)
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Error al obtener el GeoJSON: {str(e)}'}, status=500)
