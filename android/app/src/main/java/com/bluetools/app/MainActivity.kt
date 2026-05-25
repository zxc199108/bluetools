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

    private val REQUEST_ENABLE_BT = 1
    private val REQUEST_PERMISSIONS = 2

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (BluetoothDevice.ACTION_FOUND == intent.action) {
                val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                if (device != null) {
                    addDeviceButton(device)
                }
            } else if (BluetoothAdapter.ACTION_DISCOVERY_FINISHED == intent.action) {
                statusText.text = "Scan finished"
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

        checkPermissions()

        scanBtn.setOnClickListener { startScan() }
        connectBtn.setOnClickListener { connectToDevice() }
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

        // Show already-paired devices
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
    }

    private fun startScan() {
        checkPermissions()
        deviceList.removeAllViews()
        showPairedDevices()

        val filter = IntentFilter().apply {
            addAction(BluetoothDevice.ACTION_FOUND)
            addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED)
        }
        registerReceiver(receiver, filter)
        bt.scan {}
    }

    private fun addDeviceButton(device: BluetoothDevice) {
        val name = device.name ?: device.address
        val btn = Button(this).apply {
            text = "$name\n${device.address}"
            textSize = 12f
            setOnClickListener {
                selectedDevice = device
                statusText.text = "Selected: $name"
            }
        }
        deviceList.addView(btn)
    }

    private fun connectToDevice() {
        val device = selectedDevice
        if (device == null) {
            Toast.makeText(this, "Select a device first", Toast.LENGTH_SHORT).show()
            return
        }
        bt.connect(device)
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
