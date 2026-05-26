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
    private lateinit var outputText: TextView
    private lateinit var cmdInput: EditText
    private lateinit var ssidInput: EditText
    private lateinit var passInput: EditText
    private lateinit var connectBtn: Button
    private lateinit var scanBtn: Button
    private lateinit var disconnectBtn: Button
    private var selectedDevice: BluetoothDevice? = null
    private var msgId = AtomicInteger(0)
    private var pendingConnectDevice: BluetoothDevice? = null
    private var pendingConnect: Boolean = false

    private val REQUEST_PERMISSIONS = 2

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                BluetoothDevice.ACTION_FOUND -> {
                    val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    if (device != null && bt.isTarget(device)) {
                        addDeviceButton(device)
                    }
                }
                BluetoothAdapter.ACTION_DISCOVERY_FINISHED -> {
                    statusText.text = "Scan finished"
                }
                BluetoothDevice.ACTION_BOND_STATE_CHANGED -> {
                    val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    val state = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, -1)
                    if (device != null && bt.isTarget(device)) {
                        when (state) {
                            BluetoothDevice.BOND_BONDED -> {
                                statusText.text = "Paired! Connecting..."
                                if (pendingConnect && pendingConnectDevice?.address == device.address) {
                                    pendingConnect = false
                                    pendingConnectDevice = null
                                    bt.connect(device)
                                }
                            }
                            BluetoothDevice.BOND_NONE -> {
                                if (pendingConnect && pendingConnectDevice?.address == device.address) {
                                    statusText.text = "Pairing failed. Try system settings first."
                                    pendingConnect = false
                                    pendingConnectDevice = null
                                }
                            }
                            BluetoothDevice.BOND_BONDING -> {
                                statusText.text = "Pairing... Check phone for PIN."
                            }
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
        outputText = findViewById(R.id.output_text)
        cmdInput = findViewById(R.id.cmd_input)
        ssidInput = findViewById(R.id.ssid_input)
        passInput = findViewById(R.id.pass_input)
        connectBtn = findViewById(R.id.connect_btn)
        scanBtn = findViewById(R.id.scan_btn)
        disconnectBtn = findViewById(R.id.disconnect_btn)

        bt = BluetoothHelper(
            onStatus = { runOnUiThread { statusText.text = it } },
            onData = { runOnUiThread { appendOutput(it) } },
            onConnected = { connected ->
                runOnUiThread {
                    connectBtn.isEnabled = !connected
                    disconnectBtn.isEnabled = connected
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

        scanBtn.setOnClickListener { startScan() }
        connectBtn.setOnClickListener { connectOrPair() }
        disconnectBtn.setOnClickListener { bt.disconnect() }

        findViewById<Button>(R.id.ping_btn).setOnClickListener { sendJson("ping") }
        findViewById<Button>(R.id.scan_wifi_btn).setOnClickListener { sendJson("wifi_scan") }
        findViewById<Button>(R.id.wifi_connect_btn).setOnClickListener {
            val ssid = ssidInput.text.toString().trim()
            val pass = passInput.text.toString()
            if (ssid.isEmpty()) {
                Toast.makeText(this, "Enter SSID", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            sendWifiConnect(ssid, pass)
        }
        findViewById<Button>(R.id.cmd_btn).setOnClickListener {
            val cmd = cmdInput.text.toString().trim()
            if (cmd.isEmpty()) return@setOnClickListener
            sendCommand(cmd)
        }

        showPairedDevices()
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

        if (needed.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, needed.toTypedArray(), REQUEST_PERMISSIONS)
        }
    }

    private fun showPairedDevices() {
        deviceList.removeAllViews()
        bt.getPairedDevices().forEach { addDeviceButton(it) }
        if (bt.getPairedDevices().isEmpty()) {
            val tv = TextView(this).apply {
                text = "(no paired Bluetools)\nTap Scan to find devices"
                textSize = 12f
                setTextColor(0xFF666666.toInt())
                setPadding(4, 16, 4, 16)
            }
            deviceList.addView(tv)
        }
    }

    private fun startScan() {
        checkPermissions()
        deviceList.removeAllViews()
        showPairedDevices()
        bt.startDiscovery()
        statusText.text = "Scanning... (only Bluetools)"
    }

    private fun addDeviceButton(device: BluetoothDevice) {
        val name = device.name ?: device.address
        val bonded = device.bondState == BluetoothDevice.BOND_BONDED
        val label = if (bonded) "$name ✓\n${device.address}" else "$name\n${device.address}"
        val btn = Button(this).apply {
            text = label
            textSize = 12f
            setOnClickListener {
                selectedDevice = device
                statusText.text = "Selected: $name"
            }
        }
        deviceList.addView(btn)
    }

    private fun connectOrPair() {
        val device = selectedDevice
        if (device == null) {
            Toast.makeText(this, "Select a device first", Toast.LENGTH_SHORT).show()
            return
        }
        if (device.bondState == BluetoothDevice.BOND_BONDED) {
            bt.connect(device)
        } else {
            pendingConnect = true
            pendingConnectDevice = device
            bt.pair(device)
        }
    }

    private fun sendJson(type: String) {
        val id = msgId.incrementAndGet()
        val json = JSONObject().apply {
            put("type", type)
            put("id", id)
        }
        bt.send(json.toString())
    }

    private fun sendWifiConnect(ssid: String, password: String) {
        val id = msgId.incrementAndGet()
        val json = JSONObject().apply {
            put("type", "wifi_connect")
            put("id", id)
            put("ssid", ssid)
            put("password", password)
        }
        bt.send(json.toString())
    }

    private fun sendCommand(cmd: String) {
        val id = msgId.incrementAndGet()
        val json = JSONObject().apply {
            put("type", "cmd")
            put("id", id)
            put("command", cmd)
            put("args", org.json.JSONArray())
        }
        bt.send(json.toString())
    }

    private fun appendOutput(text: String) {
        outputText.append("$text\n")
    }

    override fun onDestroy() {
        unregisterReceiver(receiver)
        bt.disconnect()
        super.onDestroy()
    }
}
