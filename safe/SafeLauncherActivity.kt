package com.eian.fotoorden

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Minimal independent entry point, to retain a way to read errors when the gallery UI crashes.
 * No photo permission, MediaStore, AI model or Google Drive action is performed on launch.
 */
class SafeLauncherActivity : Activity() {
    private val bg = Color.rgb(10,16,32)
    private val fg = Color.rgb(239,244,250)
    private val mint = Color.rgb(115,213,194)
    private lateinit var info: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = bg
        window.navigationBarColor = bg
        val scroll = ScrollView(this).apply { setBackgroundColor(bg) }
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(30), dp(22), dp(28))
        }
        scroll.addView(column)
        setContentView(scroll)
        addText(column, "✦ FotoOrden IA", 28f, fg, true)
        addText(column, "Versión 0.3 · Arranque protegido", 15f, mint, true)
        addText(column, "Tus fotografías permanecen en el móvil. La app nunca las borra sin autorización.", 14f, fg, false)
        info = TextView(this).apply {
            textSize = 14f
            setTextColor(Color.rgb(190,208,225))
            setPadding(0, dp(15), 0, dp(15))
        }
        column.addView(info)
        button(column, "Abrir mi galería", true) {
            startActivity(Intent(this, MainActivity::class.java))
        }
        button(column, "Conectar con ChatGPT · Google Drive", false) {
            startActivity(Intent(this, DriveBridgeActivity::class.java))
        }
        button(column, "Ver diagnóstico de errores", false) {
            val report = FotoOrdenApplication.report(this)
            android.app.AlertDialog.Builder(this)
                .setTitle(if (report == null) "Sin errores guardados" else "Último cierre inesperado")
                .setMessage(report ?: "No hay ningún fallo registrado por esta versión.")
                .setNeutralButton("Compartir informe") { _, _ ->
                    if (report != null) {
                        val share = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, report)
                        }
                        startActivity(Intent.createChooser(share, "Compartir diagnóstico"))
                    }
                }.setPositiveButton("Cerrar", null).show()
        }
        button(column, "Borrar diagnóstico (no fotos)", false) {
            FotoOrdenApplication.clear(this)
            refresh()
        }
        refresh()
    }

    private fun refresh() {
        val report = FotoOrdenApplication.report(this)
        info.text = if (report == null)
            "Estado: preparada. El análisis no comenzará solo: abre la galería y pulsa «Analizar galería» cuando quieras."
        else
            "Se ha registrado un cierre inesperado. Pulsa «Ver diagnóstico de errores» y compárteme el texto para localizar la causa."
    }
    override fun onResume() { super.onResume(); if (::info.isInitialized) refresh() }
    private fun addText(root: LinearLayout, value: String, size: Float, color: Int, bold: Boolean) {
        root.addView(TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(null, Typeface.BOLD)
            setPadding(0, dp(10), 0, dp(10))
        })
    }
    private fun button(root: LinearLayout, label: String, primary: Boolean, click: () -> Unit) {
        val btn = Button(this).apply {
            text = label
            textSize = 14f
            isAllCaps = false
            setTextColor(if (primary) bg else fg)
            background = GradientDrawable().apply {
                setColor(if (primary) mint else Color.rgb(39,53,73))
                cornerRadius = dp(12).toFloat()
            }
            setOnClickListener { click() }
        }
        root.addView(btn, LinearLayout.LayoutParams(-1, dp(50)).apply { bottomMargin = dp(13) })
    }
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
}
