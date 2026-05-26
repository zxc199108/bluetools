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
import android.view.Gravity
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
    private lateinit var pageDevices: View
    private lateinit var pageTerminal: View
    private lateinit var pageWifi: View
    private lateinit var tabDevices: TextView
    private lateinit var tabTerminal: TextView
    private lateinit var tabWifi: TextView
    private lateinit var connectBtn: Button
    private lateinit var disconnectBtn: Button
    private var selectedDevice: BluetoothDevice? = null
    private var msgId = AtomicInteger(0)
    private var pendingConnectDevice: BluetoothDevice? = null
    private var pendingConnect = false
    private val cmdHistory = mutableListOf<String>()
    private var historyIdx = -1

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
            onData = { runOnUiThread { appendOutput(it) } },
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

        // ── Tab switching ──
        tabDevices.setOnClickListener { switchTab(pageDevices, tabDevices) }
        tabTerminal.setOnClickListener { switchTab(pageTerminal, tabTerminal) }
        tabWifi.setOnClickListener { switchTab(pageWifi, tabWifi) }

        // ── Device page ──
        findViewById<Button>(R.id.scan_btn).setOnClickListener { startScan() }
        connectBtn.setOnClickListener { connectOrPair() }
        disconnectBtn.setOnClickListener { bt.disconnect() }

        // ── Terminal page ──
        findViewById<Button>(R.id.terminal_send).setOnClickListener { sendTerminal() }
        termInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) { sendTerminal(); true } else false
        }
        findViewById<Button>(R.id.term_ping).setOnClickListener { sendTerminalCmd("ping") }
        findViewById<Button>(R.id.term_uptime).setOnClickListener { sendTerminalCmd("uptime") }
        findViewById<Button>(R.id.term_df).setOnClickListener { sendTerminalCmd("df -h") }
        findViewById<Button>(R.id.term_free).setOnClickListener { sendTerminalCmd("free") }
        findViewById<Button>(R.id.term_ps).setOnClickListener { sendTerminalCmd("ps") }
        findViewById<Button>(R.id.term_clear).setOnClickListener { termOutput.text = "" }

        // ── WiFi page ──
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

    private fun switchTab(page: View, tab: TextView) {
        pageDevices.visibility = View.GONE
        pageTerminal.visibility = View.GONE
        pageWifi.visibility = View.GONE
        page.visibility = View.VISIBLE
        tabDevices.setTextColor(0xFF666666.toInt())
        tabTerminal.setTextColor(0xFF666666.toInt())
        tabWifi.setTextColor(0xFF666666.toInt())
        tab.setTextColor(0xFF00d4aa.toInt())
    }

    // ── Terminal ──
    private fun sendTerminal() {
        val text = termInput.text.toString().trim()
        if (text.isEmpty()) return
        cmdHistory.add(text)
        historyIdx = cmdHistory.size
        appendOutput("$ $text")
        termInput.text.clear()

        try {
            val json = JSONObject(text)
            if (!json.has("type")) {
                // raw command → wrap as cmd
                val wrapped = JSONObject().apply {
                    put("type", "cmd")
                    put("id", msgId.incrementAndGet())
                    put("command", text)
                    put("args", org.json.JSONArray())
                }
                bt.send(wrapped.toString())
            } else {
                bt.send(text)
            }
        } catch (_: Exception) {
            // not JSON → raw command
            val id = msgId.incrementAndGet()
            val wrapped = JSONObject().apply {
                put("type", "cmd"); put("id", id); put("command", text); put("args", org.json.JSONArray())
            }
            bt.send(wrapped.toString())
        }
    }

    private fun sendTerminalCmd(cmd: String) {
        appendOutput("$ $cmd")
        val id = msgId.incrementAndGet()
        val json = JSONObject().apply {
            put("type", "cmd"); put("id", id); put("command", cmd); put("args", org.json.JSONArray())
        }
        bt.send(json.toString())
    }

    private fun appendOutput(text: String) {
        termOutput.append("$text\n")
        termScroll.post { termScroll.fullScroll(View.FOCUS_DOWN) }
    }

    // ── Device ──
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

    private fun sendJson(type: String) {
        bt.send(JSONObject().apply { put("type", type); put("id", msgId.incrementAndGet()) }.toString())
    }

    override fun onDestroy() {
        unregisterReceiver(receiver)
        bt.disconnect()
        super.onDestroy()
    }
}
