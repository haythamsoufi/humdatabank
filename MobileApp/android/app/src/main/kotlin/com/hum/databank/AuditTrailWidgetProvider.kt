package com.hum.databank

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import android.widget.RemoteViews
import es.antonborri.home_widget.HomeWidgetLaunchIntent
import es.antonborri.home_widget.HomeWidgetProvider
import org.json.JSONArray
import org.json.JSONException

/**
 * Home screen widget backed by [home_widget] + Flutter [audit_trail_home_widget_sync.dart].
 * Reads JSON from the same SharedPreferences key as iOS UserDefaults: [audit_trail_json].
 */
class AuditTrailWidgetProvider : HomeWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray,
        widgetData: SharedPreferences,
    ) {
        val json = widgetData.getString("audit_trail_json", null)
        val body = formatAuditBody(context, json)

        appWidgetIds.forEach { widgetId ->
            val views =
                RemoteViews(context.packageName, R.layout.audit_trail_widget).apply {
                    val pending =
                        HomeWidgetLaunchIntent.getActivity(
                            context,
                            MainActivity::class.java,
                            Uri.parse("humdatabank://"),
                        )
                    setOnClickPendingIntent(R.id.audit_trail_widget_root, pending)
                    setTextViewText(R.id.audit_trail_widget_body, body)
                }
            appWidgetManager.updateAppWidget(widgetId, views)
        }
    }

    private fun formatAuditBody(context: Context, json: String?): String {
        if (json.isNullOrBlank()) {
            return context.getString(R.string.audit_trail_widget_empty)
        }
        return try {
            val arr = JSONArray(json)
            val sb = StringBuilder()
            val limit = minOf(arr.length(), 12)
            for (i in 0 until limit) {
                val o = arr.getJSONObject(i)
                val desc = o.optString("description", "")
                val act = o.optString("activity_type", "")
                val user = o.optString("user", "")
                val ts = o.optString("timestamp", "")
                if (desc.isNotEmpty()) {
                    sb.append("• ").append(desc).append('\n')
                }
                val parts = mutableListOf<String>()
                if (act.isNotEmpty()) parts.add(act)
                if (user.isNotEmpty()) parts.add(user)
                if (ts.isNotEmpty()) parts.add(ts)
                if (parts.isNotEmpty()) {
                    sb.append("  ").append(parts.joinToString(" · ")).append("\n\n")
                }
            }
            val out = sb.toString().trimEnd()
            if (out.isEmpty()) {
                context.getString(R.string.audit_trail_widget_empty)
            } else {
                out
            }
        } catch (_: JSONException) {
            context.getString(R.string.audit_trail_widget_empty)
        }
    }
}
