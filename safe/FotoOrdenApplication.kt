package com.eian.fotoorden

import android.app.Application
import android.content.Context
import android.os.Build
import android.os.Process
import java.io.PrintWriter
import java.io.StringWriter

/**
 * Private on-device crash report. This app has no INTERNET permission.
 * A crash report is never transmitted automatically.
 */
class FotoOrdenApplication : Application() {
    companion object {
        const val REPORT = "fotoorden_last_crash.txt"
        fun report(context: Context): String? = try {
            context.openFileInput(REPORT).bufferedReader().use { it.readText() }.takeIf { it.isNotBlank() }
        } catch (_: Exception) { null }
        fun clear(context: Context) { context.deleteFile(REPORT) }
    }

    override fun onCreate() {
        super.onCreate()
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, crash ->
            try {
                val stack = StringWriter()
                PrintWriter(stack).use { crash.printStackTrace(it) }
                val safeInfo = "FotoOrden IA / Android ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})\n" +
                    "Marca y modelo: ${Build.MANUFACTURER} ${Build.MODEL}\n" +
                    "Momento: ${System.currentTimeMillis()}\n" +
                    "Hilo: ${thread.name}\n\n" + stack.toString().take(20000)
                openFileOutput(REPORT, MODE_PRIVATE).bufferedWriter().use { it.write(safeInfo) }
            } catch (_: Throwable) {
                // Never replace the original crash with a reporting crash.
            }
            if (defaultHandler != null) defaultHandler.uncaughtException(thread, crash)
            else Process.killProcess(Process.myPid())
        }
    }
}
