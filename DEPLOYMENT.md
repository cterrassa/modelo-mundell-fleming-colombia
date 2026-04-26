# Despliegue publico con dominio propio

La aplicacion es una app Streamlit. Para que cualquier persona pueda accederla desde internet se necesita:

1. Un repositorio Git, preferiblemente GitHub.
2. Un servicio de hosting para aplicaciones Python dinamicas.
3. Un dominio propio y acceso al panel DNS del registrador.

## Opcion recomendada: Render

Render permite desplegar servicios web Python, asigna una URL publica `*.onrender.com`, permite agregar dominios propios y emite certificados HTTPS automaticamente.

### 1. Subir el proyecto a GitHub

Sube esta carpeta como repositorio:

```text
modelo_mundell_fleming_colombia/
```

El archivo de entrada de la app es:

```text
app/app.py
```

### 2. Crear el servicio en Render

Puedes usar el archivo `render.yaml` incluido o crear el servicio manualmente.

Configuracion manual equivalente:

```text
Runtime: Python
Build command: pip install --upgrade pip && pip install -r requirements.txt
Start command: streamlit run app/app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true --browser.gatherUsageStats false
Health check path: /_stcore/health
```

Render debe crear una URL publica temporal, por ejemplo:

```text
https://modelo-mundell-fleming-colombia.onrender.com
```

### 3. Asociar dominio propio

En Render:

1. Abre el servicio web.
2. Ve a `Settings`.
3. Busca `Custom Domains`.
4. Agrega el dominio o subdominio, por ejemplo:

```text
mf-colombia.tudominio.com
```

5. Render mostrara los registros DNS requeridos.
6. En el panel DNS de tu proveedor de dominio, crea los registros indicados.
7. Vuelve a Render y presiona `Verify`.

Cuando la verificacion termine, Render emitira y renovara el certificado HTTPS.

### 4. Recomendacion de dominio

Es mas simple publicar primero en un subdominio:

```text
mf-colombia.tudominio.com
```

Despues, si quieres, puedes moverlo al dominio raiz:

```text
tudominio.com
```

## Opcion rapida: Streamlit Community Cloud

Streamlit Community Cloud es muy conveniente para una URL publica `*.streamlit.app`.

No es la mejor opcion si necesitas un dominio completamente propio, pero sirve para compartir rapido:

```text
https://nombre-elegido.streamlit.app
```

Configuracion:

```text
Repository: tu repositorio GitHub
Branch: main
Main file path: app/app.py
```

## Verificacion despues del despliegue

Abre:

```text
https://tu-dominio/_stcore/health
```

Debe responder:

```text
ok
```

Luego prueba:

```text
https://tu-dominio
```

## Notas importantes

- Esta app no necesita base de datos externa.
- Los datos procesados viajan dentro del repositorio en `data_processed/`.
- Si quieres que la app se recalibre automaticamente con datos nuevos, conviene crear un job separado para ejecutar `src/download_data.py`, `src/process_data.py` y `src/make_charts.py`.
- No subas credenciales privadas al repositorio.
- Si el repositorio contiene la carpeta del proyecto dentro de otra carpeta superior, configura `Root Directory` en Render para apuntar a `modelo_mundell_fleming_colombia`.
