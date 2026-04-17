# Synology DSM 7 UI Komponenten — Referenz

Gesammelte Erkenntnisse aus der Entwicklung von iCloud Photo Sync und Analyse von Cloud Sync.
Nicht offiziell dokumentiert — basiert auf Reverse Engineering und praktischer Nutzung.

---

## SYNO.SDS.* — Application Framework

### SYNO.SDS.AppInstance
Einstiegspunkt einer DSM-App. Wird vom Desktop-Launcher instanziert.

```js
Ext.define("SYNO.SDS.MyApp.Instance", {
    extend: "SYNO.SDS.AppInstance",
    appWindowName: "SYNO.SDS.MyApp.MainWindow",
    constructor: function (config) {
        this.callParent([config]);
    }
});
```

### SYNO.SDS.AppWindow
Hauptfenster der App — verhält sich wie ein Desktop-Fenster mit Titelleiste, Minimize/Maximize.

```js
Ext.define("SYNO.SDS.MyApp.MainWindow", {
    extend: "SYNO.SDS.AppWindow",
    constructor: function (config) {
        var cfg = Ext.apply({
            title: "Meine App",
            width: 900,
            height: 560,
            minWidth: 750,
            minHeight: 450,
            resizable: true,
            maximizable: true,
            minimizable: true,
            layout: "border",
            items: [/* panels */]
        }, config);
        this.callParent([cfg]);
    }
});
```

**Nützliche Methoden:**
- `this.getMsgBox()` — Zugriff auf DSM MessageBox
  - `.confirmDelete(title, msg, callback)` — Lösch-Bestätigung
  - `.alert(title, msg)` — Hinweis-Dialog
  - `.confirm(title, msg, callback)` — Ja/Nein Dialog

### SYNO.SDS.ModalWindow
Modaler Dialog (z.B. für Wizards, Login-Formulare).

```js
Ext.define("SYNO.SDS.MyApp.MyDialog", {
    extend: "SYNO.SDS.ModalWindow",
    constructor: function (config) {
        var cfg = Ext.apply({
            title: "Dialog Titel",
            width: 450,
            height: 280,
            resizable: false,
            layout: "card",       // Für mehrseitige Wizards
            activeItem: 0,
            items: [panel1, panel2],
            fbar: {               // Footer-Buttons
                items: [cancelBtn, submitBtn]
            }
        }, config);
        this.callParent([cfg]);
    }
});
```

### SYNO.SDS.Utils.FileChooser.Chooser
Nativer DSM-Datei/Ordner-Auswahldialog. Zeigt Shared Folders an.

```js
var chooser = new SYNO.SDS.Utils.FileChooser.Chooser({
    owner: this.appWin,           // Parent window (Pflicht)
    title: "Zielordner auswählen",
    usage: { type: "chooseDir" }, // "chooseDir" oder "open"
    folderToolbar: true           // Toolbar zum Erstellen neuer Ordner
});

chooser.on("choose", function (chooser, path) {
    // path = z.B. "/photo/iCloud" (virtueller Share-Pfad)
    chooser.close();
});

chooser.show();
```

**Hinweis:** Gibt virtuelle Pfade zurück (`/home/...`, `/photo/...`), nicht `/volume1/...`.
Muss serverseitig aufgelöst werden: `/home/X` → `/volume1/homes/<user>/X`, `/photo/X` → `/volume1/photo/X`.

---

## SYNO.ux.* — Widget-Bibliothek

### SYNO.ux.Button
Standard-DSM-Button. Unterstützt blauen Stil und Disabled-State.

```js
new SYNO.ux.Button({
    text: "Speichern",
    btnStyle: "blue",             // Blauer Button (alternativ: cls)
    cls: "syno-ux-button-blue",   // Alternatives Blue-Styling (wie Cloud Sync)
    width: 105,                   // Optional, oder flex verwenden
    height: 28,
    disabled: false,
    handler: function () { /* ... */ }
});
```

**Styles:**
- Standard: Grauer Button mit Rahmen
- `btnStyle: "blue"` oder `cls: "syno-ux-button-blue"`: Blauer Button
- `disabled: true`: Ausgegraut, nicht klickbar

### SYNO.ux.TabPanel
Tab-Container. Unterstützt Tab-Wechsel-Events.

```js
new SYNO.ux.TabPanel({
    region: "center",
    activeTab: 0,
    plain: true,                  // Ohne 3D-Rahmen
    cls: "my-tabs",               // Eigene CSS-Klasse
    items: [tab1, tab2, tab3],
    listeners: {
        tabchange: function (panel, newTab) {
            // Tab wurde gewechselt
        }
    }
});
```

**CSS-Anpassung der Tab-Höhe (z.B. an Toolbar angleichen):**
```css
.my-tabs > .x-tab-panel-header { padding: 0 12px; height: 45px; border-bottom: 1px solid #e0e5eb; }
.my-tabs .x-tab-strip-wrap { padding-top: 8px; }
.my-tabs .x-tab-strip li { margin-right: 8px; }
.my-tabs .x-tab-strip a { padding: 8px 16px; }
```

### SYNO.ux.FormPanel
Formular-Panel mit Label/Field-Layout. Basis für Einstellungen und Dialoge.

```js
new SYNO.ux.FormPanel({
    border: false,
    autoScroll: true,
    bodyStyle: "padding: 20px; background: #fff;",
    labelWidth: 140,
    defaults: { anchor: "100%" },
    items: [
        { xtype: "syno_fieldset", title: "Gruppe", items: [/* fields */] }
    ],
    fbar: {                       // Footer-Buttons
        items: [saveBtn]
    }
});
```

**Nützliche Methoden:**
- `.getForm().getValues()` — Alle Feldwerte als Object
- `.getForm().setValues({...})` — Felder befüllen
- `.getForm().findField("name")` — Feld per Name finden

### SYNO.ux.GridPanel
Tabelle mit Spalten, Sortierung, Auswahl.

```js
new SYNO.ux.GridPanel({
    store: myStore,
    border: false,
    columns: [
        { header: "Name", dataIndex: "name", width: 200 },
        { header: "Wert", dataIndex: "value", id: "val-col",
          renderer: function (val) { return Ext.util.Format.htmlEncode(val); }
        }
    ],
    autoExpandColumn: "val-col",  // Diese Spalte füllt den Rest
    viewConfig: {
        forceFit: false,
        emptyText: "Keine Einträge"
    },
    bbar: pagingToolbar            // Paging unten
});
```

### SYNO.ux.PagingToolbar
Seitennavigation für GridPanels mit serverseitigem Paging.

```js
new SYNO.ux.PagingToolbar({
    store: myStore,
    pageSize: 50,
    displayInfo: true,
    displayButtons: true,
    displayMsg: "Einträge {0} - {1} von {2}",
    emptyMsg: "Keine Einträge"
});
```

Der Store muss `url`, `root`, `totalProperty` definiert haben. Die Toolbar sendet automatisch `start` und `limit` Parameter.

### SYNO.ux.ComboBox
Dropdown-Auswahl. Auch als `xtype: "syno_combobox"` in FormPanels nutzbar.

```js
new SYNO.ux.ComboBox({
    fieldLabel: "Auswahl",        // In FormPanels
    name: "my_field",
    store: new Ext.data.ArrayStore({
        fields: ["val", "label"],
        data: [["opt1", "Option 1"], ["opt2", "Option 2"]]
    }),
    displayField: "label",
    valueField: "val",
    mode: "local",
    triggerAction: "all",
    editable: false,              // Nur Auswahl, keine Texteingabe
    value: "opt1",                // Default
    anchor: "100%",               // Volle Breite (in FormPanel)
    width: 120,                   // Feste Breite (in Toolbar)
    listeners: {
        select: function (combo, record) {
            var val = record.get("val");
        }
    }
});
```

### SYNO.ux.TextFilter
Textfeld mit Filter-Styling (leicht abgerundete Ecken, Suchfeld-Look).

```js
new SYNO.ux.TextFilter({
    fieldLabel: "Pfad",
    name: "target_dir",
    value: "/volume1/photo/iCloud",
    emptyText: "Pfad eingeben...",
    flex: 1,
    anchor: "100%"
});
```

---

## syno_* XTypes — Formular-Elemente

Diese werden als `xtype` in `items`-Arrays von FormPanels verwendet.

### syno_fieldset
Gruppierung von Formularfeldern mit Titel und Rahmen.

```js
{ xtype: "syno_fieldset", title: "Allgemein", items: [
    // Formularfelder hier
]}
```

### syno_combobox
Dropdown in Formularen (gleich wie `SYNO.ux.ComboBox`, aber als xtype).

```js
{ xtype: "syno_combobox",
  fieldLabel: "Intervall",
  name: "interval",
  store: new Ext.data.ArrayStore({
      fields: ["val", "label"],
      data: [[1, "1 Stunde"], [6, "6 Stunden"], [24, "Täglich"]]
  }),
  displayField: "label", valueField: "val",
  mode: "local", triggerAction: "all", editable: false,
  value: 6, anchor: "100%" }
```

### syno_checkbox
Checkbox mit Label rechts neben der Box.

```js
{ xtype: "syno_checkbox",
  fieldLabel: "Aktiviert",        // Label links
  name: "enabled",
  boxLabel: "Feature aktivieren", // Text rechts neben Checkbox
  checked: true }
```

### syno_textfield
Textfeld für Eingaben.

```js
{ xtype: "syno_textfield",
  fieldLabel: "Apple ID",
  name: "apple_id",
  allowBlank: false,
  emptyText: "name@example.com" }
```

Für Passwortfelder:
```js
{ xtype: "syno_textfield",
  fieldLabel: "Passwort",
  name: "password",
  inputType: "password",
  allowBlank: false }
```

### syno_displayfield
Nur-Lese-Textanzeige in Formularen.

```js
{ xtype: "syno_displayfield",
  fieldLabel: "Info",
  value: "Nur zur Anzeige" }
```

---

## Cloud Sync UI-Patterns

Erkenntnisse aus der Analyse der installierten Cloud Sync App auf DSM 7.2.

### Verbindungsliste (West Panel)
Cloud Sync verwendet `SYNO.ux.ModuleList` (undokumentiert, erweitert es).
Alternativ funktioniert `Ext.DataView` mit eigenem CSS gut:

```js
new Ext.DataView({
    store: myStore,
    tpl: new Ext.XTemplate(
        '<tpl for=".">',
        '<div class="connection-item">',
        '<div class="icon"></div>',
        '<div class="name">{name}</div>',
        '<div class="badge badge-ok"></div>',
        '</div>',
        '</tpl>'
    ),
    itemSelector: "div.connection-item",
    singleSelect: true
});
```

### Status-Karte (Overview)
Cloud Sync zeigt eine Karte mit großem Icon + Titel + Untertitel + Aktions-Button:
- Grüner Haken: "Auf neuestem Stand"
- Blaue rotierende Pfeile: "Synchronisierung läuft..."
- Rotes Ausrufezeichen: "Fehler"

### Toolbar-Buttons (Cloud Sync Style)
Cloud Sync nutzt `SYNO.ux.Button` mit `cls: "syno-ux-button-blue"` und feste Höhe 28px.
Buttons füllen die Toolbar-Breite mit `flex`.

### Privilege-Konfiguration
Cloud Sync nutzt `"run-as": "root"` in `conf/privilege` — das ist aber nur für Synology-signierte Packages erlaubt.
Community-Packages müssen `"run-as": "package"` verwenden und den Package-User manuell zur `administrators` Gruppe hinzufügen:

```bash
# In scripts/postinst:
/usr/syno/sbin/synogroup --memberadd administrators iCloudPhotoSync
```

---

## Toolbar-Patterns

### Buttons links, Element rechts (z.B. Log-Level Dropdown)
```js
tbar: [
    new SYNO.ux.Button({ text: "Aktualisieren", handler: fn }),
    new SYNO.ux.Button({ text: "Löschen", handler: fn }),
    "->",  // Filler — alles danach ist rechtsbündig
    { xtype: "label", text: "Level:", style: "font-size: 12px; color: #666; margin-right: 6px;" },
    myComboBox
]
```

### Flex-Buttons (volle Breite)
```js
layout: { type: "hbox" },
items: [
    new SYNO.ux.Button({ text: "+", flex: 2, cls: "syno-ux-button-blue" }),
    { xtype: "spacer", width: 6 },
    new SYNO.ux.Button({ text: "−", flex: 1 })
]
```

---

## Nützliche Ext JS Basis-Klassen (in DSM verfügbar)

| Klasse | Verwendung |
|--------|-----------|
| `Ext.Panel` | Basis-Container mit Layout |
| `Ext.DataView` | Template-basierte Datenansicht |
| `Ext.data.JsonStore` | JSON-Datenquelle (mit url/baseParams für Server) |
| `Ext.data.ArrayStore` | Statische Daten für Dropdowns |
| `Ext.XTemplate` | HTML-Templates mit Logik (`<tpl for>`, `<tpl if>`) |
| `Ext.util.Format.htmlEncode()` | XSS-sichere Textausgabe |
| `Ext.get("element-id")` | DOM-Element als Ext.Element |
| `Ext.apply(target, source)` | Object-Merge (wie Object.assign) |

---

## CSS-Klassen (DSM-intern)

| Klasse | Beschreibung |
|--------|-------------|
| `syno-ux-button-blue` | Blauer Button-Stil |
| `x-view-selected` | Ausgewähltes DataView-Item |
| `x-grid3-row` | Grid-Zeile |
| `x-grid3-row-over` | Grid-Zeile bei Hover |
| `x-tab-panel-header` | Tab-Leiste |
| `x-tab-strip` | Tab-Strip Container |
| `x-panel-body` | Panel-Inhalt |
| `x-border-layout-ct` | Border-Layout Container |
