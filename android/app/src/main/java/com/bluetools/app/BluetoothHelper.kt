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
        val SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb")
        const val TARGET = "Bluetools"
    }

    private val adapter = BluetoothAdapter.getDefaultAdapter()
    private var socket: BluetoothSocket? = null
    private var input: BufferedReader? = null
    private var output: OutputStream? = null
    private var job: Job? = null

    fun isTarget(d: BluetoothDevice) = (d.name ?: "").contains(TARGET, true)
    fun getPairedDevices() = adapter?.bondedDevices?.filter { isTarget(it) } ?: emptyList()
    fun startDiscovery() { adapter?.startDiscovery() }

    fun pair(d: BluetoothDevice) {
        onStatus("Pairing...")
        d.createBond()
    }

    fun connect(device: BluetoothDevice) {
        job?.cancel()
        job = CoroutineScope(Dispatchers.IO).launch {
            try {
                onStatus("Connecting...")
                socket = null

                try { socket = device.createInsecureRfcommSocketToServiceRecord(SPP_UUID); socket?.connect() }
                catch (_: Exception) { try { socket?.close() } catch (_: Exception) {} }

                if (socket == null || !socket!!.isConnected) {
                    try { socket?.close() } catch (_: Exception) {}
                    try { socket = device.createRfcommSocketToServiceRecord(SPP_UUID); socket?.connect() }
                    catch (_: Exception) { try { socket?.close() } catch (_: Exception) {} }
                }

                if (socket == null || !socket!!.isConnected) {
                    try { socket?.close() } catch (_: Exception) {}
                    try {
                        val m = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
                        socket = m.invoke(device, 1) as BluetoothSocket
                        socket?.connect()
                    } catch (_: Exception) { try { socket?.close() } catch (_: Exception) {} }
                }

                if (socket == null || !socket!!.isConnected)
                    throw IOException("Cannot connect")

                input = BufferedReader(InputStreamReader(socket!!.inputStream))
                output = socket!!.outputStream
                onConnected(true)
                withContext(Dispatchers.Main) { onStatus("Connected") }

                while (isActive) {
                    val line = input?.readLine() ?: break
                    if (line.isNotBlank())
                        withContext(Dispatchers.Main) { onData(line) }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) { onStatus("Err: ${e.message}"); disconnect() }
            }
        }
    }

    fun send(data: String) {
        try {
            val msg = if (data.endsWith("\n")) data else "$data\n"
            output?.write(msg.toByteArray()); output?.flush()
        } catch (_: Exception) { onStatus("Send fail") }
    }

    fun disconnect() {
        job?.cancel()
        try { input?.close() } catch (_: Exception) {}
        try { output?.close() } catch (_: Exception) {}
        try { socket?.close() } catch (_: Exception) {}
        input = null; output = null; socket = null
        onConnected(false)
        onStatus("Disconnected")
    }
}
