from pathlib import Path

root = Path("FotoOrdenIA_Android")
manifest = root / "app/src/main/AndroidManifest.xml"
m = manifest.read_text()
old = '''<application
        android:allowBackup="false"'''
new = '''<application
        android:name=".FotoOrdenApplication"
        android:allowBackup="false"'''
assert old in m
m = m.replace(old, new, 1)
old = '''<activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>'''
new = '''<activity android:name=".MainActivity" android:exported="false" />
        <activity android:name=".SafeLauncherActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>'''
assert old in m
manifest.write_text(m.replace(old, new, 1))
srcdir = root / "app/src/main/java/com/eian/fotoorden"
for fn in ["FotoOrdenApplication.kt", "SafeLauncherActivity.kt"]:
    (srcdir / fn).write_bytes((Path("safe") / fn).read_bytes())

gradle = root / "app/build.gradle.kts"
g = gradle.read_text()
assert 'versionCode = 2' in g
g = g.replace('versionCode = 2', 'versionCode = 3').replace('versionName = "0.2.0-beta"', 'versionName = "0.3.0-safe"')
gradle.write_text(g)

main = srcdir / "MainActivity.kt"
t = main.read_text()
assert 'if (hasMediaAccess()) reloadMedia(true) else askForMediaAccess()' in t
t = t.replace('if (hasMediaAccess()) reloadMedia(true) else askForMediaAccess()',
              'if (hasMediaAccess()) reloadMedia(false) else askForMediaAccess()', 1)
assert '                reloadMedia(true)' in t
t = t.replace('                reloadMedia(true)', '                reloadMedia(false)', 1)
t = t.replace('        adapter.dispose()', '        if (::adapter.isInitialized) adapter.dispose()')
t = t.replace('    private var currentlyRunning = false',
              '    private var currentlyRunning = false\n    private var receiverRegistered = false')
old = '''        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver,
            IntentFilter(AiScanService.ACTION_STATUS), Context.RECEIVER_NOT_EXPORTED)
        else @Suppress("DEPRECATION") registerReceiver(receiver, IntentFilter(AiScanService.ACTION_STATUS))
        val pref'''
new = '''        try {
            if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver,
                IntentFilter(AiScanService.ACTION_STATUS), Context.RECEIVER_NOT_EXPORTED)
            else @Suppress("DEPRECATION") registerReceiver(receiver, IntentFilter(AiScanService.ACTION_STATUS))
            receiverRegistered = true
        } catch (e: Exception) {
            receiverRegistered = false
            android.util.Log.e("FotoOrdenIA", "No se pudo registrar el monitor", e)
        }
        val pref'''
assert old in t
t = t.replace(old, new, 1)
old = '''    override fun onStop() {
        unregisterReceiver(receiver)
        super.onStop()
    }'''
new = '''    override fun onStop() {
        if (receiverRegistered) {
            try { unregisterReceiver(receiver) } catch (e: Exception) {
                android.util.Log.w("FotoOrdenIA", "Receiver ya retirado", e)
            }
            receiverRegistered = false
        }
        super.onStop()
    }'''
assert old in t
t = t.replace(old, new, 1)
main.write_text(t)
print("PATCH_OK safe launcher + crash reporter + manual scan + receiver recovery + version 3")
