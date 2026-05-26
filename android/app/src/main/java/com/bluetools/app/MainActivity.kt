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
import java.util.concurrent.atomic.AtomicInteger

class MainActivity : AppCompatActivity() {

    private lateinit var bt: BluetoothHelper
    private lateinit var statusText: TextView
    private lateinit var deviceList: LinearLayout
    private lateinit var termOutput: TextView
    private lateinit var termScroll: ScrollView
    private lateinit var termInput: EditText
    private lateinit var logOutput: TextView
    private lateinit var pageDevices: View
    private lateinit var pageTerminal: View
    private lateinit var pageWifi: View
    private lateinit var pageLog: View
    private lateinit var tabDevices: TextView
    private lateinit var tabTerminal: TextView
    private lateinit var tabWifi: TextView
    private lateinit var tabLog: TextView
    private lateinit var connectBtn: Button
    private lateinit var disconnectBtn: Button
    private var selectedDevice: BluetoothDevice? = null
    private var msgId = AtomicInteger(0)
    private var pendingConnectDevice: BluetoothDevice? = null
    private var pendingConnect = false
    private var terminalMode = true

    private val REQUEST_PERMISSIONS = 2

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                BluetoothDevice.ACTION_FOUND -> {
                    val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    if (device != null && bt.isTarget(device)) addDeviceButton(device)
                }
                BluetoothAdapter.ACTION_DISCOVERY_FINISHED -> statusText.text = "Scan finished"
                BluetoothDevice.ACTION_BOND_STATE_CHANGED -> {
                    val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    val state = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, -1)
                    if (device != null && bt.isTarget(device)) {
                        when (state) {
                            BluetoothDevice.BOND_BONDED -> {
                                statusText.text = "Paired! Connecting..."
                                if (pendingConnect && pendingConnectDevice?.address == device.address) {
                                    pendingConnect = false; pendingConnectDevice = null
                                    bt.connect(device)
                                }
                            }
                            BluetoothDevice.BOND_NONE -> {
                                if (pendingConnect && pendingConnectDevice?.address == device.address) {
                                    statusText.text = "Pairing failed"
                                    pendingConnect = false; pendingConnectDevice = null
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

        statusText = findViewById(R.id.status_text)
        deviceList = findViewById(R.id.device_list)
        termOutput = findViewById(R.id.terminal_output)
        termScroll = findViewById(R.id.terminal_scroll)
        termInput = findViewById(R.id.terminal_input)
        logOutput = findViewById(R.id.log_output)
        pageDevices = findViewById(R.id.page_devices)
        pageTerminal = findViewById(R.id.page_terminal)
        pageWifi = findViewById(R.id.page_wifi)
        pageLog = findViewById(R.id.page_log)
        tabDevices = findViewById(R.id.tab_devices)
        tabTerminal = findViewById(R.id.tab_terminal)
        tabWifi = findViewById(R.id.tab_wifi)
        tabLog = findViewById(R.id.tab_log)
        connectBtn = findViewById(R.id.connect_btn)
        disconnectBtn = findViewById(R.id.disconnect_btn)

        termOutput.movementMethod = ScrollingMovementMethod()
        logOutput.movementMethod = ScrollingMovementMethod()

        bt = BluetoothHelper(
            onStatus = { runOnUiThread { statusText.text = it } },
            onData = { runOnUiThread { handleData(it) } },
            onConnected = { connected ->
                runOnUiThread {
                    connectBtn.isEnabled = !connected
                    disconnectBtn.isEnabled = connected
                    if (connected) switchTab(pageTerminal, tabTerminal)
                }
            }
        )

        val filter = IntentFilter().apply {
            addAction(BluetoothDevice.ACTION_FOUND)
            addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED)
            addAction(BluetoothDevice.ACTION_BOND_STATE_CHANGED)
        }
        registerReceiver(receiver, filter)
        checkPermissions()

        tabDevices.setOnClickListener { switchTab(pageDevices, tabDevices) }
        tabTerminal.setOnClickListener { switchTab(pageTerminal, tabTerminal) }
        tabWifi.setOnClickListener { switchTab(pageWifi, tabWifi) }
        tabLog.setOnClickListener { switchTab(pageLog, tabLog) }

        findViewById<Button>(R.id.scan_btn).setOnClickListener { startScan() }
        connectBtn.setOnClickListener { connectOrPair() }
        disconnectBtn.setOnClickListener { bt.disconnect() }

        // Terminal
        findViewById<Button>(R.id.terminal_send).setOnClickListener { sendTerminal() }
        termInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) { sendTerminal(); true } else false
        }
        findViewById<Button>(R.id.term_ping).setOnClickListener { sendRaw("ping -c 2 127.0.0.1") }
        findViewById<Button>(R.id.term_uptime).setOnClickListener { sendRaw("uptime") }
        findViewById<Button>(R.id.term_df).setOnClickListener { sendRaw("df -h") }
        findViewById<Button>(R.id.term_free).setOnClickListener { sendRaw("free -h") }
        findViewById<Button>(R.id.term_ps).setOnClickListener { sendRaw("ps aux --sort=-%mem | head -10") }
        findViewById<Button>(R.id.term_clear).setOnClickListener { termOutput.text = "" }

        // WiFi
        findViewById<Button>(R.id.scan_wifi_btn).setOnClickListener { sendJson("wifi_scan") }
        findViewById<Button>(R.id.wifi_connect_btn).setOnClickListener {
            val ssid = findViewById<EditText>(R.id.ssid_input).text.toString().trim()
            val pass = findViewById<EditText>(R.id.pass_input).text.toString()
            if (ssid.isEmpty()) { Toast.makeText(this, "Enter SSID", Toast.LENGTH_SHORT).show(); return@setOnClickListener }
            val id = msgId.incrementAndGet()
            val json = JSONObject().apply { put("type", "wifi_connect"); put("id", id); put("ssid", ssid); put("password", pass) }
            bt.send(json.toString())
        }

        showPairedDevices()
    }

    private fun handleData(data: String) {
        // Try to format JSON nicely for log
        try {
            val json = org.json.JSONObject(data)
            logOutput.append(json.toString(2) + "\n")
        } catch (_: Exception) {
            // Raw text → terminal output
            termOutput.append(data + "\n")
            termScroll.post { termScroll.fullScroll(View.FOCUS_DOWN) }
        }
    }

    private fun switchTab(page: View, tab: TextView) {
        for (p in listOf(pageDevices, pageTerminal, pageWifi, pageLog)) p.visibility = View.GONE
        for (t in listOf(tabDevices, tabTerminal, tabWifi, tabLog)) t.setTextColor(0xFF666666.toInt())
        page.visibility = View.VISIBLE
        tab.setTextColor(0xFF00d4aa.toInt())
    }

    private fun sendRaw(cmd: String) {
        termOutput.append("$ $cmd\n")
        termScroll.post { termScroll.fullScroll(View.FOCUS_DOWN) }
        bt.send(cmd)
    }

    private fun sendTerminal() {
        val text = termInput.text.toString()
        if (text.isBlank()) return
        sendRaw(text.trim())
        termInput.text.clear()
    }

    private fun sendJson(type: String) {
        val id = msgId.incrementAndGet()
        bt.send(JSONObject().apply { put("type", type); put("id", id) }.toString())
    }

    private fun checkPermissions() {
        val needed = mutableListOf<String>()
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED)
                needed.add(Manifest.permission.BLUETOOTH_CONNECT)
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED)
                needed.add(Manifest.permission.BLUETOOTH_SCAN)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.ACCESS_FINE_LOCATION)
        if (needed.isNotEmpty()) ActivityCompat.requestPermissions(this, needed.toTypedArray(), REQUEST_PERMISSIONS)
    }

    private fun showPairedDevices() {
        deviceList.removeAllViews()
        bt.getPairedDevices().forEach { addDeviceButton(it) }
        if (bt.getPairedDevices().isEmpty()) {
            val tv = TextView(this).apply {
                text = "(no paired Bluetools)\nTap Scan"
                textSize = 12f; setTextColor(0xFF666666.toInt()); setPadding(4, 16, 4, 16)
            }
            deviceList.addView(tv)
        }
    }

    private fun startScan() {
        checkPermissions()
        deviceList.removeAllViews()
        showPairedDevices()
        bt.startDiscovery()
        statusText.text = "Scanning..."
    }

    private fun addDeviceButton(device: BluetoothDevice) {
        val name = device.name ?: device.address
        val bonded = device.bondState == BluetoothDevice.BOND_BONDED
        val label = if (bonded) "$name ✓\n${device.address}" else "$name\n${device.address}"
        val btn = Button(this).apply {
            text = label; textSize = 12f
            setOnClickListener { selectedDevice = device; statusText.text = "Selected: $name" }
        }
        deviceList.addView(btn)
    }

    private fun connectOrPair() {
        val device = selectedDevice ?: run { Toast.makeText(this, "Select a device", Toast.LENGTH_SHORT).show(); return }
        if (device.bondState == BluetoothDevice.BOND_BONDED) bt.connect(device)
        else { pendingConnect = true; pendingConnectDevice = device; bt.pair(device) }
    }

    override fun onDestroy() {
        unregisterReceiver(receiver)
        bt.disconnect()
        super.onDestroy()
    }
}
