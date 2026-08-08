

[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/andybrandt-mcp-simple-timeserver-badge.png)](https://mseep.ai/app/andybrandt-mcp-simple-timeserver)

# MCP Simple Timeserver
[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/andybrandt/mcp-simple-timeserver)](https://archestra.ai/mcp-catalog/andybrandt__mcp-simple-timeserver)
[![smithery badge](https://smithery.ai/badge/mcp-simple-timeserver)](https://smithery.ai/server/mcp-simple-timeserver)

*Una de las decisiones de diseño curiosas que tomó Anthropic fue privar a Claude de las marcas de tiempo para los mensajes enviados por el usuario en claude.ai, así como de la hora actual en general. ¡El pobre Claude no puede saber qué hora es! `mcp-simple-timeserver` es un servidor MCP sencillo que soluciona esto.*

## Herramientas Disponibles

Este servidor proporciona las siguientes herramientas:

| Herramienta | Descripción |
|------|-------------|
| `get_local_time` | Devuelve la hora local actual, el día de la semana y la zona horaria desde la máquina del usuario |
| `get_utc` | Devuelve la hora UTC precisa desde un [servidor de tiempo NTP](https://en.wikipedia.org/wiki/Network_Time_Protocol) |
| `get_current_time` | Devuelve la hora actual con conversiones opcionales de ubicación, zona horaria y calendario |
| `calculate_time_distance` | Calcula la duración entre dos fechas/horas (cuentas regresivas, tiempo transcurrido) |
| `get_holidays` | Devuelve los días festivos públicos (y opcionalmente vacaciones escolares) para un país |
| `is_holiday` | Verifica si una fecha específica es festiva en un país o ciudad dada |

Todas las herramientas (excepto `get_local_time`) utilizan la hora precisa de los servidores NTP. Si NTP no está disponible, alternan automáticamente a la hora local del servidor con una notificación.

### Soporte de ubicación mediante `get_current_time`

La herramienta `get_current_time` admite parámetros de ubicación para obtener la hora local en cualquier lugar del mundo:

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `city` | Nombre de la ciudad (caso de uso principal) | `"Warsaw"`, `"Tokyo"`, `"New York"` |
| `country` | Nombre del país o código ISO | `"Poland"`, `"JP"`, `"United States"` |
| `timezone` | Zona horaria IANA o desplazamiento UTC | `"Europe/Warsaw"`, `"+05:30"` |

Prioridad: `timezone` > `city` > `country`. Cuando se proporciona la ubicación, la respuesta incluye la hora local, información de la zona horaria, desplazamiento UTC y estado de DST (horario de verano).

Si hoy es un día festivo en la ubicación especificada, se mostrará en la salida.

### Soporte de calendario mediante `get_current_time`

La herramienta `get_current_time` también acepta un parámetro opcional `calendar` con una lista de formatos de calendario separados por comas:

| Calendario | Descripción |
|----------|-------------|
| `unix` | Marca de tiempo Unix (segundos desde 1970-01-01) |
| `isodate` | Fecha semanal ISO 8601 (ej., `2026-W03-6`) |
| `hijri` | Calendario lunar islámico/Hijri |
| `japanese` | Calendario de Era japonesa (devuelve inglés y Kanji) |
| `hebrew` | Calendario hebreo/judío (devuelve inglés y hebreo, incluye festividades) |
| `persian` | Calendario persa/Jalali (devuelve inglés y farsi) |

Ejemplo: `get_current_time(city="Tokyo", calendar="japanese")` devuelve la hora local de Tokio con el calendario de Era japonesa.

### Cálculo de distancia temporal mediante `calculate_time_distance`

Calcule la duración entre dos fechas u horas:

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `from_date` | Fecha de inicio (ISO 8601 o "now") | `"2025-01-15"`, `"now"` |
| `to_date` | Fecha de fin (ISO 8601 o "now") | `"2025-12-31"`, `"2025-06-01T17:00:00"` |
| `unit` | Formato de salida | `"auto"`, `"days"`, `"weeks"`, `"hours"`, `"minutes"`, `"seconds"` |
| `business_days` | Contar solo de lunes a viernes (basado en fecha, inclusivo) | `true` |
| `exclude_holidays` | Excluir también días festivos públicos (requiere country/city) | `true` |

Los parámetros de ubicación (`city`, `country`, `timezone`) también se pueden usar para especificar el contexto de la zona horaria.

Cuando `business_days=true`, la hora del día se ignora y las fechas se cuentan como días completos (puntos finales inclusivos).
El parámetro `unit` se ignora en este modo. Las festividades se excluyen solo cuando caen en días laborables.

Ejemplo: `calculate_time_distance(from_date="now", to_date="2025-12-31")` devuelve una cuenta regresiva hacia Nochevieja.
Ejemplo: `calculate_time_distance(from_date="2026-01-26", to_date="2026-01-30", business_days=true, exclude_holidays=true, city="Sydney")` devuelve la cantidad de días laborables en ese rango.

### Información de festividades mediante `get_holidays` y `is_holiday`

Obtenga información de festividades públicas y vacaciones escolares para ~119 países:

**Parámetros de `get_holidays`:**

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `country` | Nombre del país o código ISO (requerido) | `"Poland"`, `"DE"`, `"United States"` |
| `year` | Año para obtener las festividades (predeterminado: año actual) | `2026` |
| `include_school_holidays` | Incluir períodos de vacaciones escolares | `true` |

**Parámetros de `is_holiday`:**

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `country` | Nombre del país o código ISO | `"Poland"`, `"US"` |
| `city` | Nombre de la ciudad para información específica de la región | `"Warsaw"`, `"Munich"` |
| `date` | Fecha a verificar en formato ISO (predeterminado: hoy) | `"2026-01-01"` |

**Vacaciones escolares regionales**: Al usar el parámetro `city` con `is_holiday`, las vacaciones escolares se filtran para mostrar solo aquellas que afectan a la región específica. Esto es particularmente útil en países donde las vacaciones escolares varían según la región (por ejemplo, voivodatos polacos, estados alemanes, comunidades autónomas españolas).

Ejemplo: `is_holiday(city="Warsaw", date="2026-01-19")` devuelve información de vacaciones escolares específica para el voivodato de Mazowieckie.

**Fuentes de datos**:
- Festividades públicas: [Nager.Date API](https://date.nager.at/) (119 países)
- Vacaciones escolares: [OpenHolidaysAPI](https://openholidaysapi.org/) (36 países, principalmente europeos)

## Instalación

### Instalación mediante Smithery

Para instalar Simple Timeserver para Claude Desktop automáticamente mediante [Smithery](https://smithery.ai/server/mcp-simple-timeserver):

```bash
npx -y @smithery/cli install mcp-simple-timeserver --client claude
```

### Instalación manual
Primero instale el módulo utilizando:

```bash
pip install mcp-simple-timeserver

```

Luego configure en el cliente MCP - la [aplicación de escritorio de Claude](https://claude.ai/download).

En Mac OS se verá así:

```json
"mcpServers": {
  "simple-timeserver": {
    "command": "python",
    "args": ["-m", "mcp_simple_timeserver"]
  }
}
```

En Windows debe verificar la ruta a su ejecutable de Python utilizando `where python` en `cmd` (línea de comandos de Windows). 

La configuración típica se verá así:

```json
"mcpServers": {
  "simple-timeserver": {
    "command": "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
    "args": ["-m", "mcp_simple_timeserver"]
  }
}
```

## Variante de servidor web

Este proyecto también incluye una versión alojable en red que puede implementarse como un servidor web independiente. Para instrucciones sobre cómo ejecutar y desplegarlo, consulte la [Guía de implementación del servidor web](WEB_DEPLOYMENT.md).

O simplemente puede usar mi servidor añadiéndolo en https://mcp.andybrandt.net/timeserver a Claude y otras herramientas que admiten MCP.
