package com.bluetools.app

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import kotlinx.coroutines.*
import java.io.*
import java.util.UUID

class BluetoothHelper(
    private val onStatus: (String) -> Unit,
    private val onData: (String) -> Unit,
    private val onConnected: (Boolean) -> Unit
) {
    companion object {
        val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb")
    }

    private val adapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var socket: BluetoothSocket? = null
    private var input: BufferedReader? = null
    private var output: OutputStream? = null
    private var job: Job? = null

    fun isEnabled() = adapter?.isEnabled == true

    fun getPairedDevices(): Set<BluetoothDevice> =
        adapter?.bondedDevices ?: emptySet()

    fun scan(callback: (BluetoothDevice) -> Unit) {
        if (!isEnabled()) {
            onStatus("Please enable Bluetooth first")
            return
        }
        onStatus("Scanning...")
        val filter = android.content.IntentFilter(BluetoothDevice.ACTION_FOUND)
        // Use startDiscovery for classic Bluetooth scan
        adapter?.startDiscovery()
        onStatus("Scan started. Select device from list.")
    }

    fun pair(device: BluetoothDevice, pin: String) {
        onStatus("Pairing with ${device.name ?: device.address}...")
        try {
            val m = device.javaClass.getMethod("setPin", ByteArray::class.java)
            m.invoke(device, pin.toByteArray())
            device.createBond()
            onStatus("Pairing started. Check phone for PIN prompt.")
        } catch (e: Exception) {
            onStatus("Pairing error: ${e.message}. Try pairing from system settings first.")
        }
    }

    fun connect(device: BluetoothDevice) {
        job?.cancel()
        job = CoroutineScope(Dispatchers.IO).launch {
            try {
                onStatus("Connecting to ${device.name ?: device.address}...")
                socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
                socket?.connect()
                input = BufferedReader(InputStreamReader(socket!!.inputStream))
                output = socket!!.outputStream
                onConnected(true)
                withContext(Dispatchers.Main) { onStatus("Connected!") }

                while (isActive) {
                    val line = input?.readLine() ?: break
                    if (line.isNotBlank()) {
                        withContext(Dispatchers.Main) { onData(line) }
                    }
                }
            } catch (e: IOException) {
                withContext(Dispatchers.Main) {
                    onStatus("Connection error: ${e.message}")
                    disconnect()
                }
            }
        }
    }

    fun send(data: String) {
        try {
            val msg = if (data.endsWith("\n")) data else "$data\n"
            output?.write(msg.toByteArray())
            output?.flush()
        } catch (e: Exception) {
            onStatus("Send error: ${e.message}")
        }
    }

    fun disconnect() {
        job?.cancel()
        try { input?.close() } catch (_: Exception) {}
        try { output?.close() } catch (_: Exception) {}
        try { socket?.close() } catch (_: Exception) {}
        input = null
        output = null
        socket = null
        onConnected(false)
        onStatus("Disconnected")
    }
}
