/*
 * btagent.c — Minimal BlueZ pairing agent in C.
 * Compile: gcc -o btagent btagent.c $(pkg-config --cflags --libs glib-2.0 gio-2.0)
 * 
 * Auto-accepts all pairing requests with fixed PIN.
 * No GATT, no SPP, no D-Bus object manager — just Agent1.
 */
#include <gio/gio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *PIN = "1234";
static GMainLoop *loop = NULL;

/* org.freedesktop.DBus.Properties.GetAll */
static GVariant *
handle_get_all(GDBusConnection *conn, const gchar *sender,
               const gchar *path, const gchar *iface,
               const gchar *method, GVariant *params,
               GDBusMethodInvocation *invoc, gpointer user_data)
{
    if (g_strcmp0(iface, "org.freedesktop.DBus.Properties") != 0) {
        g_dbus_method_invocation_return_dbus_error(invoc,
            "org.freedesktop.DBus.Error.InvalidArgs", "Unknown interface");
        return NULL;
    }
    GVariantBuilder builder;
    g_variant_builder_init(&builder, G_VARIANT_TYPE("a{sv}"));
    g_variant_builder_add(&builder, "{sv}", "Capability",
                          g_variant_new_string("DisplayOnly"));
    g_dbus_method_invocation_return_value(invoc,
        g_variant_new("(a{sv})", &builder));
    return NULL;
}

/* org.bluez.Agent1.Release */
static GVariant *
handle_release(GDBusConnection *conn, const gchar *sender,
               const gchar *path, const gchar *iface,
               const gchar *method, GVariant *params,
               GDBusMethodInvocation *invoc, gpointer user_data)
{
    g_print("[agent] Release\n");
    g_dbus_method_invocation_return_value(invoc, NULL);
    return NULL;
}

/* org.bluez.Agent1.RequestPinCode */
static GVariant *
handle_pincode(GDBusConnection *conn, const gchar *sender,
               const gchar *path, const gchar *iface,
               const gchar *method, GVariant *params,
               GDBusMethodInvocation *invoc, gpointer user_data)
{
    g_print("[agent] RequestPinCode -> %s\n", PIN);
    g_dbus_method_invocation_return_value(invoc,
        g_variant_new("(s)", PIN));
    return NULL;
}

/* org.bluez.Agent1.DisplayPinCode */
static GVariant *
handle_display_pin(GDBusConnection *conn, const gchar *sender,
                   const gchar *path, const gchar *iface,
                   const gchar *method, GVariant *params,
                   GDBusMethodInvocation *invoc, gpointer user_data)
{
    const gchar *pin;
    g_variant_get(params, "(&os)", NULL, &pin);
    g_print("[agent] DisplayPinCode: %s\n", pin);
    g_dbus_method_invocation_return_value(invoc, NULL);
    return NULL;
}

/* org.bluez.Agent1.RequestPasskey */
static GVariant *
handle_passkey(GDBusConnection *conn, const gchar *sender,
               const gchar *path, const gchar *iface,
               const gchar *method, GVariant *params,
               GDBusMethodInvocation *invoc, gpointer user_data)
{
    guint32 pk = (guint32)atoi(PIN);
    g_print("[agent] RequestPasskey -> %u\n", pk);
    g_dbus_method_invocation_return_value(invoc,
        g_variant_new("(u)", pk));
    return NULL;
}

/* org.bluez.Agent1.DisplayPasskey */
static GVariant *
handle_display_passkey(GDBusConnection *conn, const gchar *sender,
                       const gchar *path, const gchar *iface,
                       const gchar *method, GVariant *params,
                       GDBusMethodInvocation *invoc, gpointer user_data)
{
    guint32 pk;
    guint16 entered;
    g_variant_get(params, "(&ouq)", NULL, &pk, &entered);
    g_print("[agent] DisplayPasskey: %u\n", pk);
    g_dbus_method_invocation_return_value(invoc, NULL);
    return NULL;
}

/* org.bluez.Agent1.RequestConfirmation (accept) */
static GVariant *
handle_confirm(GDBusConnection *conn, const gchar *sender,
               const gchar *path, const gchar *iface,
               const gchar *method, GVariant *params,
               GDBusMethodInvocation *invoc, gpointer user_data)
{
    guint32 pk;
    g_variant_get(params, "(&ou)", NULL, &pk);
    g_print("[agent] Confirm %u -> accept\n", pk);
    g_dbus_method_invocation_return_value(invoc, NULL);
    return NULL;
}

/* org.bluez.Agent1.RequestAuthorization (accept) */
static GVariant *
handle_auth(GDBusConnection *conn, const gchar *sender,
            const gchar *path, const gchar *iface,
            const gchar *method, GVariant *params,
            GDBusMethodInvocation *invoc, gpointer user_data)
{
    g_print("[agent] Authorize -> accept\n");
    g_dbus_method_invocation_return_value(invoc, NULL);
    return NULL;
}

/* org.bluez.Agent1.AuthorizeService (accept) */
static GVariant *
handle_auth_svc(GDBusConnection *conn, const gchar *sender,
                const gchar *path, const gchar *iface,
                const gchar *method, GVariant *params,
                GDBusMethodInvocation *invoc, gpointer user_data)
{
    const gchar *uuid;
    g_variant_get(params, "(&os)", NULL, &uuid);
    g_print("[agent] AuthorizeService %s -> accept\n", uuid);
    g_dbus_method_invocation_return_value(invoc, NULL);
    return NULL;
}

/* org.bluez.Agent1.Cancel */
static GVariant *
handle_cancel(GDBusConnection *conn, const gchar *sender,
              const gchar *path, const gchar *iface,
              const gchar *method, GVariant *params,
              GDBusMethodInvocation *invoc, gpointer user_data)
{
    g_print("[agent] Cancel\n");
    g_dbus_method_invocation_return_value(invoc, NULL);
    return NULL;
}

static const GDBusInterfaceVTable agent_vtable = {
    .method_call = NULL,  /* handled via individual registrations below */
};

/* Register individual methods */
static void
register_method(GDBusConnection *conn, const char *method,
                const char *in_sig, const char *out_sig,
                GDBusInterfaceMethodFunc handler)
{
    GDBusInterfaceInfo *iface;
    GDBusMethodInfo *mi;
    GVariant *result;

    GError *error = NULL;
    GDBusNodeInfo *node = g_dbus_node_info_new_for_xml(
        "<node>"
        "  <interface name='org.bluez.Agent1'>"
        "    <method name='Release'/>"
        "    <method name='RequestPinCode'><arg type='s' direction='out'/></method>"
        "    <method name='DisplayPinCode'><arg type='s' direction='in'/></method>"
        "    <method name='RequestPasskey'><arg type='u' direction='out'/></method>"
        "    <method name='DisplayPasskey'><arg type='u' direction='in'/><arg type='q' direction='in'/></method>"
        "    <method name='RequestConfirmation'><arg type='u' direction='in'/></method>"
        "    <method name='RequestAuthorization'/>"
        "    <method name='AuthorizeService'><arg type='s' direction='in'/></method>"
        "    <method name='Cancel'/>"
        "  </interface>"
        "</node>", &error);
    if (!node) {
        g_printerr("Failed to parse XML: %s\n", error->message);
        g_error_free(error);
        return;
    }
    g_dbus_connection_register_object(conn, "/org/bluetools/agent",
        node->interfaces[0], &agent_vtable, NULL, NULL, NULL);

    /* Now register method handlers manually */
    static const struct {
        const char *name;
        GDBusInterfaceMethodFunc handler;
    } methods[] = {
        {"Release", handle_release},
        {"RequestPinCode", handle_pincode},
        {"DisplayPinCode", handle_display_pin},
        {"RequestPasskey", handle_passkey},
        {"DisplayPasskey", handle_display_passkey},
        {"RequestConfirmation", handle_confirm},
        {"RequestAuthorization", handle_auth},
        {"AuthorizeService", handle_auth_svc},
        {"Cancel", handle_cancel},
        {NULL, NULL}
    };

    for (int i = 0; methods[i].name; i++) {
        if (g_strcmp0(method, methods[i].name) == 0) {
            /* Already registered via the node info, actually. 
               The node info registration handles dispatch, we just
               need the handler in the vtable. But easier: use conn directly */
            break;
        }
    }
    g_dbus_node_info_unref(node);
}

int main(int argc, char **argv) {
    const char *pin = argc > 1 ? argv[1] : PIN;
    PIN = pin;

    GDBusConnection *conn = g_bus_get_sync(G_BUS_TYPE_SYSTEM, NULL, NULL);
    if (!conn) {
        g_printerr("Failed to connect to system D-Bus\n");
        return 1;
    }

    GError *error = NULL;
    GDBusNodeInfo *node = g_dbus_node_info_new_for_xml(
        "<node>"
        "  <interface name='org.bluez.Agent1'>"
        "    <method name='Release'/>"
        "    <method name='RequestPinCode'><arg type='s' direction='out'/></method>"
        "    <method name='DisplayPinCode'><arg type='s' direction='in'/></method>"
        "    <method name='RequestPasskey'><arg type='u' direction='out'/></method>"
        "    <method name='DisplayPasskey'><arg type='u' direction='in'/><arg type='q' direction='in'/></method>"
        "    <method name='RequestConfirmation'><arg type='u' direction='in'/></method>"
        "    <method name='RequestAuthorization'/>"
        "    <method name='AuthorizeService'><arg type='s' direction='in'/></method>"
        "    <method name='Cancel'/>"
        "  </interface>"
        "  <interface name='org.freedesktop.DBus.Properties'>"
        "    <method name='GetAll'><arg type='s' direction='in'/><arg type='a{sv}' direction='out'/></method>"
        "  </interface>"
        "</node>", &error);
    if (!node) {
        g_printerr("XML parse error: %s\n", error->message);
        return 1;
    }

    /* Register as D-Bus object with all methods */
    static const GDBusInterfaceVTable vtable = {
        .method_call = NULL,
        .get_property = NULL,
        .set_property = NULL,
    };

    guint reg_id = g_dbus_connection_register_object(
        conn, "/org/bluetools/agent",
        node->interfaces[0], &vtable, NULL, NULL, &error);
    if (!reg_id) {
        g_printerr("Register object failed: %s\n", error->message);
        return 1;
    }

    /* Also register Properties interface */
    g_dbus_connection_register_object(
        conn, "/org/bluetools/agent",
        node->interfaces[1], &vtable, NULL, NULL, NULL);

    /* Register handlers via raw method_call */
    typedef struct {
        const char *iface;
        const char *method;
        GDBusInterfaceMethodFunc handler;
    } Handler;

    Handler handlers[] = {
        {"org.bluez.Agent1", "Release", handle_release},
        {"org.bluez.Agent1", "RequestPinCode", handle_pincode},
        {"org.bluez.Agent1", "DisplayPinCode", handle_display_pin},
        {"org.bluez.Agent1", "RequestPasskey", handle_passkey},
        {"org.bluez.Agent1", "DisplayPasskey", handle_display_passkey},
        {"org.bluez.Agent1", "RequestConfirmation", handle_confirm},
        {"org.bluez.Agent1", "RequestAuthorization", handle_auth},
        {"org.bluez.Agent1", "AuthorizeService", handle_auth_svc},
        {"org.bluez.Agent1", "Cancel", handle_cancel},
        {"org.freedesktop.DBus.Properties", "GetAll", handle_get_all},
        {NULL, NULL, NULL}
    };

    for (int i = 0; handlers[i].iface; i++) {
        /* Create introspection data and register */
        GDBusInterfaceInfo *iface_info = g_new0(GDBusInterfaceInfo, 1);
        iface_info->name = g_strdup(handlers[i].iface);

        GDBusMethodInfo *mi = g_new0(GDBusMethodInfo, 1);
        mi->name = g_strdup(handlers[i].method);
        iface_info->methods = mi;

        static GDBusInterfaceVTable vt = { .method_call = handlers[i].handler };
        g_dbus_connection_register_object(conn, "/org/bluetools/agent",
            iface_info, &vt, NULL, NULL, NULL);
    }

    /* Register agent with BlueZ */
    GVariant *result = g_dbus_connection_call_sync(
        conn, "org.bluez", "/org/bluez",
        "org.bluez.AgentManager1", "RegisterAgent",
        g_variant_new("(os)", "/org/bluetools/agent", "DisplayOnly"),
        NULL, G_DBUS_CALL_FLAGS_NONE, -1, NULL, &error);

    if (!result) {
        g_printerr("RegisterAgent failed: %s\n", error->message);
        g_clear_error(&error);
        return 1;
    }
    g_variant_unref(result);

    /* Set as default agent */
    result = g_dbus_connection_call_sync(
        conn, "org.bluez", "/org/bluez",
        "org.bluez.AgentManager1", "RequestDefaultAgent",
        g_variant_new("(o)", "/org/bluetools/agent"),
        NULL, G_DBUS_CALL_FLAGS_NONE, -1, NULL, &error);

    if (!result) {
        g_printerr("RequestDefaultAgent failed: %s\n", error->message);
        g_clear_error(&error);
        return 1;
    }
    g_variant_unref(result);

    g_print("[agent] Registered (DisplayOnly, PIN=%s)\n", pin);

    loop = g_main_loop_new(NULL, FALSE);
    g_main_loop_run(loop);

    g_dbus_connection_unregister_object(conn, reg_id);
    g_object_unref(conn);
    g_main_loop_unref(loop);
    return 0;
}
