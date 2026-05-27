package com.bluetools.app

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.method.ScrollingMovementMethod
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private lateinit var bt: BluetoothHelper
    private lateinit var statusText: TextView
    private lateinit var deviceList: LinearLayout
    private lateinit var termOutput: TextView
    private lateinit var termScroll: ScrollView
    private lateinit var termInput: EditText
    private lateinit var pageDevices: View
    private lateinit var pageTerminal: View
    private lateinit var pageWifi: View
    private lateinit var tabDevices: TextView
    private lateinit var tabTerminal: TextView
    private lateinit var tabWifi: TextView
    private lateinit var connectBtn: Button
    private lateinit var disconnectBtn: Button
    private var selectedDevice: BluetoothDevice? = null
    private var pendingConnect = false
    private var pendingDevice: BluetoothDevice? = null

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                BluetoothDevice.ACTION_FOUND -> {
                    val d = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    if (d != null && bt.isTarget(d)) addDevice(d)
                }
                BluetoothAdapter.ACTION_DISCOVERY_FINISHED -> statusText.text = "Scan done"
                BluetoothDevice.ACTION_BOND_STATE_CHANGED -> {
                    val d = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    val s = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, -1)
                    if (d != null && bt.isTarget(d)) {
                        when (s) {
                            BluetoothDevice.BOND_BONDED -> {
                                statusText.text = "Paired. Connecting..."
                                if (pendingConnect && pendingDevice?.address == d.address) {
                                    pendingConnect = false; pendingDevice = null
                                    bt.connect(d)
                                }
                            }
                            BluetoothDevice.BOND_NONE -> {
                                if (pendingConnect && pendingDevice?.address == d.address) {
                                    pendingConnect = false; pendingDevice = null
                                    statusText.text = "Pairing failed"
                                }
                            }
                            BluetoothDevice.BOND_BONDING -> statusText.text = "Pairing..."
                        }
                    }
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        checkPermissions() // Android 12+蓝牙权限

        statusText = findViewById(R.id.status_text)
        deviceList = findViewById(R.id.device_list)
        termOutput = findViewById(R.id.term_output)
        termScroll = findViewById(R.id.term_scroll)
        termInput = findViewById(R.id.term_input)
        pageDevices = findViewById(R.id.page_devices)
        pageTerminal = findViewById(R.id.page_terminal)
        pageWifi = findViewById(R.id.page_wifi)
        tabDevices = findViewById(R.id.tab_devices)
        tabTerminal = findViewById(R.id.tab_terminal)
        tabWifi = findViewById(R.id.tab_wifi)
        connectBtn = findViewById(R.id.connect_btn)
        disconnectBtn = findViewById(R.id.disconnect_btn)

        termOutput.movementMethod = ScrollingMovementMethod()

        bt = BluetoothHelper(
            onStatus = { runOnUiThread { statusText.text = it } },
            onData = { runOnUiThread { handleData(it) } },
            onConnected = { c ->
                runOnUiThread {
                    connectBtn.isEnabled = !c; disconnectBtn.isEnabled = c
                    if (c) switchTab(pageTerminal, tabTerminal)
                }
            }
        )

        registerReceiver(receiver, IntentFilter().apply {
            addAction(BluetoothDevice.ACTION_FOUND)
            addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED)
            addAction(BluetoothDevice.ACTION_BOND_STATE_CHANGED)
        })

        tabDevices.setOnClickListener { switchTab(pageDevices, tabDevices) }
        tabTerminal.setOnClickListener { switchTab(pageTerminal, tabTerminal) }
        tabWifi.setOnClickListener { switchTab(pageWifi, tabWifi) }

        findViewById<Button>(R.id.scan_btn).setOnClickListener { scan() }
        connectBtn.setOnClickListener { connectOrPair() }
        disconnectBtn.setOnClickListener { bt.disconnect() }

        findViewById<Button>(R.id.term_send).setOnClickListener { sendTerm() }
        termInput.setOnEditorActionListener { _, a, _ -> if (a == EditorInfo.IME_ACTION_SEND) { sendTerm(); true } else false }
        findViewById<Button>(R.id.btn_uptime).setOnClickListener { sendRaw("uptime") }
        findViewById<Button>(R.id.btn_df).setOnClickListener { sendRaw("df -h") }
        findViewById<Button>(R.id.btn_free).setOnClickListener { sendRaw("free -h") }
        findViewById<Button>(R.id.btn_ps).setOnClickListener { sendRaw("ps aux | head -10") }
        findViewById<Button>(R.id.btn_ls).setOnClickListener { sendRaw("ls -la") }
        findViewById<Button>(R.id.btn_clear).setOnClickListener { termOutput.text = "" }

        findViewById<Button>(R.id.scan_wifi_btn).setOnClickListener { bt.send("{\"type\":\"wifi_scan\"}") }
        findViewById<Button>(R.id.wifi_connect_btn).setOnClickListener {
            val s = findViewById<EditText>(R.id.ssid_input).text.toString().trim()
            val p = findViewById<EditText>(R.id.pass_input).text.toString()
            if (s.isEmpty()) { Toast.makeText(this, "Enter SSID", Toast.LENGTH_SHORT).show(); return@setOnClickListener }
            bt.send("{\"type\":\"wifi_connect\",\"ssid\":\"$s\",\"password\":\"$p\"}")
        }

        showPaired()
    }

    private fun handleData(raw: String) {
        try {
            val j = org.json.JSONObject(raw)
            val t = j.optString("type", "")
            when (t) {
                "cmd_result" -> {
                    val ok = j.optBoolean("success", false)
                    termOut(if (ok) j.optString("output", "OK") else "ERR: ${j.optString("output", "")}")
                }
                "raw" -> termOut(j.optString("output", ""))
                "pong" -> termOut("pong")
                "ready" -> termOut(j.optString("msg", "ready"))
                "wifi_scan_result" -> {
                    val nets = j.optJSONArray("networks")
                    if (nets != null) {
                        for (i in 0 until nets.length()) {
                            val n = nets.getJSONObject(i)
                            addWifiItem(n.optString("ssid", "?"), n.optString("signal", ""))
                        }
                    }
                }
                "wifi_connect_result" -> termOut(if (j.optBoolean("success")) "WiFi OK: ${j.optString("ip", "")}" else "WiFi FAIL: ${j.optString("error", "")}")
                "error" -> termOut("Error: ${j.optString("error", raw)}")
                else -> termOut(j.toString(2))
            }
        } catch (_: Exception) {
            termOut(raw)
        }
    }

    private fun termOut(text: String) {
        termOutput.append("$text\n")
        termScroll.post { termScroll.fullScroll(View.FOCUS_DOWN) }
    }

    private fun sendRaw(cmd: String) {
        termOut("$ $cmd")
        bt.send(cmd)
    }

    private fun sendTerm() {
        val t = termInput.text.toString().trim()
        if (t.isBlank()) return
        if (t.startsWith("{")) bt.send(t)
        else sendRaw(t)
        termInput.text.clear()
    }

    private fun switchTab(p: View, t: TextView) {
        for (v in listOf(pageDevices, pageTerminal, pageWifi)) v.visibility = View.GONE
        for (tv in listOf(tabDevices, tabTerminal, tabWifi)) tv.setTextColor(0xFF666666.toInt())
        p.visibility = View.VISIBLE
        t.setTextColor(0xFF00d4aa.toInt())
    }

    private fun checkPermissions() {
        val needed = mutableListOf<String>()
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED)
                needed.add(Manifest.permission.BLUETOOTH_CONNECT)
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED)
                needed.add(Manifest.permission.BLUETOOTH_SCAN)
        }
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.ACCESS_FINE_LOCATION)
        if (needed.isNotEmpty())
            ActivityCompat.requestPermissions(this, needed.toTypedArray(), 2)
    }

    private fun scan() {
        checkPermissions()
        deviceList.removeAllViews()
        showPaired()
        bt.startDiscovery()
        statusText.text = "Scanning..."
    }

    private fun showPaired() {
        bt.getPairedDevices().forEach { addDevice(it) }
    }

    private fun addDevice(d: BluetoothDevice) {
        val name = d.name ?: d.address
        val bonded = d.bondState == BluetoothDevice.BOND_BONDED
        val btn = Button(this).apply {
            text = if (bonded) "$name ✓" else name
            textSize = 12f
            setOnClickListener { selectedDevice = d; statusText.text = "Selected: $name" }
        }
        deviceList.addView(btn)
    }

    private fun addWifiItem(ssid: String, sig: String) {
        val list = findViewById<LinearLayout>(R.id.wifi_list)
        val btn = Button(this).apply {
            text = "$ssid  ($sig)"
            textSize = 11f
            setOnClickListener {
                findViewById<EditText>(R.id.ssid_input).setText(ssid)
                findViewById<EditText>(R.id.pass_input).requestFocus()
            }
        }
        list.addView(btn)
    }

    private fun connectOrPair() {
        val d = selectedDevice ?: run { Toast.makeText(this, "Select device", Toast.LENGTH_SHORT).show(); return }
        if (d.bondState == BluetoothDevice.BOND_BONDED) bt.connect(d)
        else { pendingConnect = true; pendingDevice = d; bt.pair(d) }
    }

    override fun onDestroy() {
        unregisterReceiver(receiver)
        bt.disconnect()
        super.onDestroy()
    }
}
