package com.insightfulgames.app.ui

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

private val dateTimeFormatter: DateTimeFormatter =
    DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT)
        .withZone(ZoneId.systemDefault())

private val dateFormatter: DateTimeFormatter =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withZone(ZoneId.systemDefault())

/** Fecha ISO 8601 UTC -> texto en la zona del teléfono. Si no se puede leer, devuelve el original. */
fun formatDateTime(iso: String?): String =
    iso?.let { runCatching { dateTimeFormatter.format(Instant.parse(it)) }.getOrDefault(it) } ?: "—"

fun formatDate(iso: String?): String =
    iso?.let { runCatching { dateFormatter.format(Instant.parse(it)) }.getOrDefault(it) } ?: "—"
