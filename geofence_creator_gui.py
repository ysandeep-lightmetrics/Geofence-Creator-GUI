import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import math
import webbrowser
import threading
import concurrent.futures
import tempfile
import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth


# ---------------------------------------------------------------------------
# Scrollable frame helper
# ---------------------------------------------------------------------------
class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._win_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Make inner frame stretch to canvas width
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Mousewheel: check if cursor is over this scrollable area
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_resize(self, event):
        self.canvas.itemconfigure(self._win_id, width=event.width)

    def _on_mousewheel(self, event):
        # Only scroll if the mouse is over this widget or its children
        widget = event.widget
        try:
            while widget is not None:
                if widget is self or widget is self.canvas or widget is self.scrollable_frame:
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return
                widget = widget.master
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Load credentials from config/.env
# ---------------------------------------------------------------------------
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", ".env"))

# ---------------------------------------------------------------------------
# Environments & credentials
# ---------------------------------------------------------------------------
ENVIRONMENTS = {
    "Production": "https://api.lightmetrics.co",
    "QA": "https://api-qa.lightmetrics.co",
    "Beta": "https://api-beta.lightmetrics.co",
}

AUTH_USERS = {
    "lmpresales": os.environ.get("LMPRESALES_PWD", ""),
    "lmqatesting1": os.environ.get("LMQATESTING1_PWD", ""),
    "lmqatesting2": os.environ.get("LMQATESTING2_PWD", ""),
}


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class GeofenceCreatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Geofence Creator Tool")
        self.root.geometry("960x820")
        self.root.minsize(800, 600)

        self.stored_property_id = tk.StringVar(value="")

        style = ttk.Style()
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # --- Tabs ---
        config_tab = ttk.Frame(notebook)
        notebook.add(config_tab, text="  Config  ")
        self._build_config_tab(config_tab)

        prop_tab = ttk.Frame(notebook)
        notebook.add(prop_tab, text="  Create Property  ")
        self._build_property_tab(prop_tab)

        geo_tab = ttk.Frame(notebook)
        notebook.add(geo_tab, text="  Create Geofence  ")
        self._build_geofence_tab(geo_tab)

        props_tab = ttk.Frame(notebook)
        notebook.add(props_tab, text="  Preview Properties  ")
        self._build_props_tab(props_tab)

        preview_tab = ttk.Frame(notebook)
        notebook.add(preview_tab, text="  Preview Device Geofences  ")
        self._build_preview_tab(preview_tab)

        activity_tab = ttk.Frame(notebook)
        notebook.add(activity_tab, text="  Activity  ")
        self._build_activity_tab(activity_tab)

        map_tab = ttk.Frame(notebook)
        notebook.add(map_tab, text="  Map Preview  ")
        self._build_map_tab(map_tab)

    # ================================================================
    # CONFIG TAB
    # ================================================================
    def _build_config_tab(self, parent):
        # ---- Environment ----
        env_frame = ttk.LabelFrame(parent, text="Environment", padding=15)
        env_frame.pack(fill=tk.X, padx=20, pady=(20, 10))

        self.env_name = tk.StringVar(value="Production")
        self.base_url = tk.StringVar(value=ENVIRONMENTS["Production"])
        self.fleet_id = tk.StringVar(value="lmfleetGuru_localTest")

        ttk.Label(env_frame, text="Environment:").grid(row=0, column=0, sticky="w", pady=5)
        env_combo = ttk.Combobox(
            env_frame,
            textvariable=self.env_name,
            values=list(ENVIRONMENTS.keys()),
            width=20,
            state="readonly",
        )
        env_combo.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        env_combo.bind("<<ComboboxSelected>>", self._on_env_change)

        self.url_label = ttk.Label(env_frame, text=self.base_url.get(), foreground="blue")
        self.url_label.grid(row=0, column=2, padx=10, pady=5, sticky="w")

        ttk.Label(env_frame, text="Fleet ID:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(env_frame, textvariable=self.fleet_id, width=40).grid(
            row=1, column=1, columnspan=2, padx=10, pady=5, sticky="w"
        )

        # ---- Auth ----
        auth_frame = ttk.LabelFrame(parent, text="Authentication", padding=15)
        auth_frame.pack(fill=tk.X, padx=20, pady=(0, 10))

        self.auth_user = tk.StringVar(value=list(AUTH_USERS.keys())[0])
        self.username = tk.StringVar(value=list(AUTH_USERS.keys())[0])
        self.password = tk.StringVar(value=list(AUTH_USERS.values())[0])

        ttk.Label(auth_frame, text="Select User:").grid(row=0, column=0, sticky="w", pady=5)
        user_combo = ttk.Combobox(
            auth_frame,
            textvariable=self.auth_user,
            values=list(AUTH_USERS.keys()) + ["Other"],
            width=25,
            state="readonly",
        )
        user_combo.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        user_combo.bind("<<ComboboxSelected>>", self._on_user_change)

        self.pwd_display = tk.StringVar(value="*" * 20)
        self.pwd_display_label = ttk.Label(auth_frame, textvariable=self.pwd_display, foreground="gray")
        ttk.Label(auth_frame, text="Password:").grid(row=1, column=0, sticky="w", pady=5)
        self.pwd_display_label.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        # Custom auth fields (hidden by default, shown when "Other" is selected)
        self.custom_auth_frame = ttk.Frame(auth_frame)
        ttk.Label(self.custom_auth_frame, text="Username:").grid(row=0, column=0, sticky="w", pady=5)
        self.custom_username_entry = ttk.Entry(self.custom_auth_frame, width=30)
        self.custom_username_entry.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        ttk.Label(self.custom_auth_frame, text="Password:").grid(row=1, column=0, sticky="w", pady=5)
        self.custom_password_entry = ttk.Entry(self.custom_auth_frame, width=30, show="*")
        self.custom_password_entry.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        self.custom_set_btn = ttk.Button(
            self.custom_auth_frame, text="Set", width=8, command=self._on_custom_auth_set
        )
        self.custom_set_btn.grid(row=2, column=1, padx=10, pady=5, sticky="w")

        # ---- Summary ----
        summary = ttk.LabelFrame(parent, text="Current Config Summary", padding=15)
        summary.pack(fill=tk.X, padx=20, pady=(0, 10))

        self.summary_text = tk.StringVar()
        self._update_summary()
        ttk.Label(summary, textvariable=self.summary_text, font=("Consolas", 10)).pack(anchor="w")

        ttk.Label(
            parent,
            text="Select environment & user from dropdowns. These are used for both Property and Geofence API calls.",
            foreground="gray",
        ).pack(padx=20, pady=5, anchor="w")

        # Bottom-center footer
        footer = ttk.Frame(parent)
        footer.pack(side="bottom", fill="x", pady=(10, 5))
        ttk.Label(
            footer,
            text="Strictly for internal use only. LightMetrics.",
            foreground="gray",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="center")
        ttk.Label(
            footer,
            text="If you have any questions or need help, contact SDK Team",
            foreground="gray",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="center")

    def _on_env_change(self, _event=None):
        env = self.env_name.get()
        url = ENVIRONMENTS.get(env, "")
        self.base_url.set(url)
        self.url_label.config(text=url)
        self._update_summary()

    def _on_user_change(self, _event=None):
        user = self.auth_user.get()
        if user == "Other":
            # Show custom input fields, hide password display
            self.pwd_display_label.grid_remove()
            self.custom_auth_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
        else:
            # Hide custom fields, show password display
            self.custom_auth_frame.grid_remove()
            self.pwd_display_label.grid()
            pwd = AUTH_USERS.get(user, "")
            self.username.set(user)
            self.password.set(pwd)
            self.pwd_display.set(pwd[:4] + "*" * 16)
        self._update_summary()

    def _on_custom_auth_set(self):
        self.username.set(self.custom_username_entry.get())
        self.password.set(self.custom_password_entry.get())
        self._update_summary()
        messagebox.showinfo("Auth Set", f"Credentials set for user: {self.username.get()}")

    def _update_summary(self):
        self.summary_text.set(
            f"ENV: {self.env_name.get()}  |  URL: {self.base_url.get()}  |  "
            f"Fleet: {self.fleet_id.get()}  |  User: {self.username.get()}"
        )

    # ================================================================
    # PROPERTY TAB
    # ================================================================
    def _build_property_tab(self, parent):
        # --- Split: left form (70%) | right preview (30%) ---
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=7)
        container.columnconfigure(1, weight=3)
        container.rowconfigure(0, weight=1)

        # Left side: scrollable form
        left_frame = ttk.Frame(container)
        left_frame.grid(row=0, column=0, sticky="nsew")

        scroll = ScrollableFrame(left_frame)
        scroll.pack(fill=tk.BOTH, expand=True)
        f = scroll.scrollable_frame

        # Right side: JSON preview + response
        right_frame = ttk.Frame(container)
        right_frame.grid(row=0, column=1, sticky="nsew")

        btn = ttk.Frame(right_frame)
        btn.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn, text="Preview JSON", command=self._preview_property).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Create Property", command=self._create_property).pack(side=tk.LEFT, padx=5)

        ttk.Label(right_frame, text="JSON Preview:", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=8, pady=(5, 0)
        )
        self.prop_resp = scrolledtext.ScrolledText(right_frame, font=("Consolas", 9), wrap=tk.WORD)
        self.prop_resp.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # ---------- Basic info ----------
        basic = ttk.LabelFrame(f, text="Basic Info", padding=10)
        basic.pack(fill=tk.X, padx=10, pady=5)

        self.prop_name = tk.StringVar()
        self.prop_desc = tk.StringVar()
        self.prop_color = tk.StringVar(value="#FF5733")

        for r, (lbl, var) in enumerate(
            [
                ("Property Name *:", self.prop_name),
                ("Description:", self.prop_desc),
                ("Colour Hex:", self.prop_color),
            ]
        ):
            ttk.Label(basic, text=lbl).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(basic, textvariable=var, width=50).grid(
                row=r, column=1, padx=5, pady=3, sticky="w"
            )

        # ---------- Alerts ----------
        alerts = ttk.LabelFrame(f, text="Geofence Alerts", padding=10)
        alerts.pack(fill=tk.X, padx=10, pady=5)

        self.alert_entry = tk.BooleanVar(value=True)
        self.alert_exit = tk.BooleanVar(value=True)
        ttk.Checkbutton(alerts, text="Geofence Entry Alert", variable=self.alert_entry).pack(anchor="w")
        ttk.Checkbutton(alerts, text="Geofence Exit Alert", variable=self.alert_exit).pack(anchor="w")

        # ---------- Rule: MEDIA_CAPTURE ----------
        self.rule_media_on = tk.BooleanVar(value=False)
        media = ttk.LabelFrame(f, text="Rule: MEDIA_CAPTURE", padding=10)
        media.pack(fill=tk.X, padx=10, pady=5)

        ttk.Checkbutton(media, text="Include this rule", variable=self.rule_media_on).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5)
        )

        self.media_action = tk.StringVar(value="ENABLE")
        self.media_file_type = tk.StringVar(value="image")
        self.media_collage = tk.StringVar(value="C1x1")
        self.media_quality = tk.StringVar(value="10")
        self.media_src_driver = tk.BooleanVar(value=True)
        self.media_src_road = tk.BooleanVar(value=False)
        self.media_resolution = tk.StringVar(value="1280x720")
        self.media_on_entry = tk.BooleanVar(value=True)
        self.media_on_exit = tk.BooleanVar(value=True)

        row = 1
        for lbl, widget_type, var, *extra in [
            ("Action:", "combo", self.media_action, ["ENABLE", "DISABLE"]),
            ("File Type:", "combo", self.media_file_type, ["image", "video"]),
            ("Collage:", "entry", self.media_collage),
            ("Quality:", "entry", self.media_quality),
            ("Resolution:", "entry", self.media_resolution),
        ]:
            ttk.Label(media, text=lbl).grid(row=row, column=0, sticky="w", pady=2)
            if widget_type == "combo":
                ttk.Combobox(media, textvariable=var, values=extra[0], width=16, state="readonly").grid(
                    row=row, column=1, sticky="w", pady=2
                )
            else:
                ttk.Entry(media, textvariable=var, width=18).grid(row=row, column=1, sticky="w", pady=2)
            row += 1

        ttk.Label(media, text="Sources:").grid(row=row, column=0, sticky="w", pady=2)
        src = ttk.Frame(media)
        src.grid(row=row, column=1, sticky="w", pady=2)
        ttk.Checkbutton(src, text="DRIVER", variable=self.media_src_driver).pack(side=tk.LEFT)
        ttk.Checkbutton(src, text="ROAD", variable=self.media_src_road).pack(side=tk.LEFT)
        row += 1

        ttk.Checkbutton(media, text="Capture on Entry", variable=self.media_on_entry).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=2
        )
        row += 1
        ttk.Checkbutton(media, text="Capture on Exit", variable=self.media_on_exit).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=2
        )

        # ---------- Rule: CONFIGURATION ----------
        self.rule_cfg_on = tk.BooleanVar(value=False)
        cfg = ttk.LabelFrame(f, text="Rule: CONFIGURATION (Asset Config)", padding=10)
        cfg.pack(fill=tk.X, padx=10, pady=5)

        ttk.Checkbutton(cfg, text="Include this rule", variable=self.rule_cfg_on).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 5)
        )

        # -- Blur config --
        self.cfg_road_blur = tk.BooleanVar(value=False)
        self.cfg_blur_mode = tk.StringVar(value="NONE")

        ttk.Label(cfg, text="Driver Blur Mode:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Combobox(
            cfg,
            textvariable=self.cfg_blur_mode,
            values=["NONE", "ALL_FACES", "PASSENGER_FACES", "ALL_EXCEPT_DRIVER"],
            width=18,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Checkbutton(cfg, text="Road Blur PII", variable=self.cfg_road_blur).grid(
            row=1, column=2, sticky="w", padx=5, pady=2
        )

        # -- All boolean config fields (from Kotlin Config data class) --
        self.cfg_anomaly = tk.BooleanVar(value=True)
        self.cfg_cornering = tk.BooleanVar(value=False)
        self.cfg_distracted = tk.BooleanVar(value=True)
        self.cfg_drowsy = tk.BooleanVar(value=False)
        self.cfg_cellphone = tk.BooleanVar(value=False)
        self.cfg_drinking = tk.BooleanVar(value=False)
        self.cfg_fatigue = tk.BooleanVar(value=True)
        self.cfg_smoking = tk.BooleanVar(value=False)
        self.cfg_texting = tk.BooleanVar(value=False)
        self.cfg_unbuckled = tk.BooleanVar(value=False)
        self.cfg_yawning = tk.BooleanVar(value=False)
        self.cfg_fcw = tk.BooleanVar(value=False)
        self.cfg_hard_braking = tk.BooleanVar(value=False)
        self.cfg_harsh_accel = tk.BooleanVar(value=True)
        self.cfg_idling = tk.BooleanVar(value=True)
        self.cfg_lane_departure = tk.BooleanVar(value=False)
        self.cfg_lane_drift = tk.BooleanVar(value=False)
        self.cfg_lizard_eye = tk.BooleanVar(value=False)
        self.cfg_max_speed = tk.BooleanVar(value=True)
        self.cfg_crash = tk.BooleanVar(value=True)
        self.cfg_rollover = tk.BooleanVar(value=False)
        self.cfg_speeding = tk.BooleanVar(value=True)
        self.cfg_stop_sign = tk.BooleanVar(value=True)
        self.cfg_tailgating = tk.BooleanVar(value=True)
        self.cfg_traffic_light = tk.BooleanVar(value=False)

        self.cfg_idle_dur = tk.StringVar(value="5")
        self.cfg_speed_limit = tk.StringVar(value="60")

        checks = [
            ("Anomaly", self.cfg_anomaly),
            ("Cornering", self.cfg_cornering),
            ("Distracted Driving", self.cfg_distracted),
            ("Drowsy Driving", self.cfg_drowsy),
            ("Cellphone Distraction", self.cfg_cellphone),
            ("Drinking Distraction", self.cfg_drinking),
            ("Driver Fatigue Detection", self.cfg_fatigue),
            ("Smoking Distraction", self.cfg_smoking),
            ("Texting Distraction", self.cfg_texting),
            ("Unbuckled Seat Belt", self.cfg_unbuckled),
            ("Yawning Detection", self.cfg_yawning),
            ("Forward Collision Warning", self.cfg_fcw),
            ("Hard Braking", self.cfg_hard_braking),
            ("Harsh Acceleration", self.cfg_harsh_accel),
            ("Idling", self.cfg_idling),
            ("Lane Departure", self.cfg_lane_departure),
            ("Lane Drift", self.cfg_lane_drift),
            ("Lizard Eye Distraction", self.cfg_lizard_eye),
            ("Max Speed", self.cfg_max_speed),
            ("Potential Crash", self.cfg_crash),
            ("Rollover", self.cfg_rollover),
            ("Speeding", self.cfg_speeding),
            ("Stop Sign", self.cfg_stop_sign),
            ("Tailgating", self.cfg_tailgating),
            ("Traffic Light", self.cfg_traffic_light),
        ]
        row = 2
        col = 0
        for text, var in checks:
            ttk.Checkbutton(cfg, text=text, variable=var).grid(
                row=row, column=col, sticky="w", padx=5, pady=1
            )
            col += 1
            if col >= 3:
                col = 0
                row += 1
        if col != 0:
            row += 1

        # Numeric fields
        ttk.Label(cfg, text="Speed Upper Limit:").grid(row=row, column=0, sticky="w", padx=5, pady=2)
        ttk.Entry(cfg, textvariable=self.cfg_speed_limit, width=8).grid(
            row=row, column=1, sticky="w", padx=5, pady=2
        )
        row += 1
        ttk.Label(cfg, text="Idling Duration (min):").grid(row=row, column=0, sticky="w", padx=5, pady=2)
        ttk.Entry(cfg, textvariable=self.cfg_idle_dur, width=8).grid(
            row=row, column=1, sticky="w", padx=5, pady=2
        )

        # ---------- Simple rules: DMS, FR, DVR, ADAS, PRIVACY (with appliesTo) ----------
        self.simple_rules = {}
        for target, default_action, sources_list in [
            ("DMS", "DISABLE", ["DRIVER", "ROAD"]),
            ("FR", "DISABLE", ["DRIVER"]),
            ("DVR", "DISABLE", []),
            ("ADAS", "DISABLE", []),
            ("PRIVACY", "ENABLE", []),
        ]:
            rule_frame = ttk.LabelFrame(f, text=f"Rule: {target}", padding=10)
            rule_frame.pack(fill=tk.X, padx=10, pady=5)

            on_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(rule_frame, text="Include this rule", variable=on_var).pack(side=tk.LEFT)

            action_var = tk.StringVar(value=default_action)
            ttk.Label(rule_frame, text="  Action:").pack(side=tk.LEFT)
            ttk.Combobox(
                rule_frame, textvariable=action_var, values=["ENABLE", "DISABLE"], width=10, state="readonly"
            ).pack(side=tk.LEFT, padx=5)

            # appliesTo checkboxes
            src_vars = {}
            if target in ("DMS", "FR", "DVR", "ADAS"):
                ttk.Label(rule_frame, text="  Applies To:").pack(side=tk.LEFT, padx=(10, 0))
                for src_name in ["DRIVER", "ROAD"]:
                    sv = tk.BooleanVar(value=(src_name in sources_list))
                    ttk.Checkbutton(rule_frame, text=src_name, variable=sv).pack(side=tk.LEFT)
                    src_vars[src_name] = sv

            self.simple_rules[target] = {
                "on": on_var,
                "action": action_var,
                "sources": src_vars,
            }

        # ---------- Rule: AIRPLANE_MODE ----------
        self.rule_airplane_on = tk.BooleanVar(value=False)
        airplane = ttk.LabelFrame(f, text="Rule: AIRPLANE_MODE", padding=10)
        airplane.pack(fill=tk.X, padx=10, pady=5)

        ttk.Checkbutton(airplane, text="Include this rule", variable=self.rule_airplane_on).pack(
            side=tk.LEFT
        )
        self.airplane_action = tk.StringVar(value="DISABLE")
        ttk.Label(airplane, text="  Action:").pack(side=tk.LEFT)
        ttk.Combobox(
            airplane, textvariable=self.airplane_action, values=["ENABLE", "DISABLE"], width=10, state="readonly"
        ).pack(side=tk.LEFT, padx=5)

        # ---------- Rule: FAR_AWAY_ASSET ----------
        self.rule_faraway_on = tk.BooleanVar(value=False)
        faraway = ttk.LabelFrame(f, text="Rule: FAR_AWAY_ASSET", padding=10)
        faraway.pack(fill=tk.X, padx=10, pady=5)

        ttk.Checkbutton(faraway, text="Include this rule", variable=self.rule_faraway_on).pack(side=tk.LEFT)
        self.faraway_action = tk.StringVar(value="ENABLE")
        ttk.Label(faraway, text="  Action:").pack(side=tk.LEFT)
        ttk.Combobox(
            faraway, textvariable=self.faraway_action, values=["ENABLE", "DISABLE"], width=10, state="readonly"
        ).pack(side=tk.LEFT, padx=5)
        self.faraway_dist = tk.StringVar(value="4")
        ttk.Label(faraway, text="  Distance (km):").pack(side=tk.LEFT)
        ttk.Entry(faraway, textvariable=self.faraway_dist, width=8).pack(side=tk.LEFT, padx=5)

    # ---- Build property payload ----
    def _build_property_payload(self):
        payload = {}

        name = self.prop_name.get().strip()
        if not name:
            messagebox.showerror("Error", "Property Name is required!")
            return None
        payload["propertyName"] = name

        desc = self.prop_desc.get().strip()
        if desc:
            payload["description"] = desc

        color = self.prop_color.get().strip()
        if color:
            payload["colourHex"] = color

        payload["geofenceAlerts"] = {
            "geofenceEntry": self.alert_entry.get(),
            "geofenceExit": self.alert_exit.get(),
        }

        rules = []

        # MEDIA_CAPTURE
        if self.rule_media_on.get():
            sources = []
            if self.media_src_driver.get():
                sources.append("DRIVER")
            if self.media_src_road.get():
                sources.append("ROAD")
            rules.append(
                {
                    "action": self.media_action.get(),
                    "target": "MEDIA_CAPTURE",
                    "fileType": self.media_file_type.get(),
                    "mediaType": [
                        {
                            "collage": self.media_collage.get(),
                            "quality": int(self.media_quality.get() or 10),
                            "sources": sources or ["DRIVER"],
                            "resolution": self.media_resolution.get(),
                        }
                    ],
                    "captureOnExit": self.media_on_exit.get(),
                    "captureOnEntry": self.media_on_entry.get(),
                }
            )

        # CONFIGURATION
        if self.rule_cfg_on.get():
            rules.append(
                {
                    "action": "ENABLE",
                    "target": "CONFIGURATION",
                    "assetConfiguration": {
                        "blurConfig": {
                            "roadBlurPII": self.cfg_road_blur.get(),
                            "driverBlurMode": self.cfg_blur_mode.get(),
                        },
                        "anomalyEnabled": self.cfg_anomaly.get(),
                        "corneringEnabled": self.cfg_cornering.get(),
                        "distractedDrivingEnabled": self.cfg_distracted.get(),
                        "drowsyDrivingEnabled": self.cfg_drowsy.get(),
                        "enableCellphoneDistraction": self.cfg_cellphone.get(),
                        "enableDrinkingDistraction": self.cfg_drinking.get(),
                        "enableDriverFatigueDetection": self.cfg_fatigue.get(),
                        "enableSmokingDistraction": self.cfg_smoking.get(),
                        "enableTextingDistraction": self.cfg_texting.get(),
                        "enableUnbuckledSeatBelt": self.cfg_unbuckled.get(),
                        "enableYawningDetection": self.cfg_yawning.get(),
                        "forwardCollisionWarningEnabled": self.cfg_fcw.get(),
                        "hardBrakingEnabled": self.cfg_hard_braking.get(),
                        "harshAccelerationEnabled": self.cfg_harsh_accel.get(),
                        "idlingEnabled": self.cfg_idling.get(),
                        "laneDepartureEnabled": self.cfg_lane_departure.get(),
                        "laneDriftEnabled": self.cfg_lane_drift.get(),
                        "lizardEyeDistractionEnabled": self.cfg_lizard_eye.get(),
                        "maxSpeedEnabled": self.cfg_max_speed.get(),
                        "potentialCrashEnabled": self.cfg_crash.get(),
                        "rollOverEnabled": self.cfg_rollover.get(),
                        "speedingEnabled": self.cfg_speeding.get(),
                        "stopSignEnabled": self.cfg_stop_sign.get(),
                        "tailgatingEnabled": self.cfg_tailgating.get(),
                        "trafficLightEnabled": self.cfg_traffic_light.get(),
                        "idlingDurationInMinute": int(self.cfg_idle_dur.get() or 5),
                        "speedUpperLimit": int(self.cfg_speed_limit.get() or 60),
                    },
                }
            )

        # Simple rules: DMS, FR, DVR, ADAS, PRIVACY
        for target, rule_data in self.simple_rules.items():
            if rule_data["on"].get():
                rule = {
                    "action": rule_data["action"].get(),
                    "target": target,
                }
                applies_to = [s for s, v in rule_data["sources"].items() if v.get()]
                if applies_to:
                    rule["appliesTo"] = applies_to
                rules.append(rule)

        # AIRPLANE_MODE
        if self.rule_airplane_on.get():
            rules.append({"action": self.airplane_action.get(), "target": "AIRPLANE_MODE"})

        # FAR_AWAY_ASSET
        if self.rule_faraway_on.get():
            rule = {"action": self.faraway_action.get(), "target": "FAR_AWAY_ASSET"}
            dist = self.faraway_dist.get().strip()
            if dist:
                rule["farAwayDistanceInKm"] = int(dist)
            rules.append(rule)

        if rules:
            payload["geofenceRules"] = rules

        return payload

    def _preview_property(self):
        payload = self._build_property_payload()
        if payload:
            self.prop_resp.delete("1.0", tk.END)
            self.prop_resp.insert(tk.END, json.dumps(payload, indent=2))

    def _create_property(self):
        payload = self._build_property_payload()
        if not payload:
            return

        url = f"{self.base_url.get().rstrip('/')}/v2/fleets/{self.fleet_id.get()}/geofences/properties"
        auth = HTTPBasicAuth(self.username.get(), self.password.get())
        headers = {"Content-Type": "application/json"}

        self.prop_resp.delete("1.0", tk.END)
        self.prop_resp.insert(tk.END, f"POST {url}\n\n")

        try:
            resp = requests.post(url, headers=headers, auth=auth, json=payload, timeout=30)
            try:
                result = resp.json()
            except Exception:
                result = resp.text

            self.prop_resp.insert(
                tk.END,
                f"Status: {resp.status_code}\n\n{json.dumps(result, indent=2) if isinstance(result, dict) else result}\n",
            )

            if isinstance(result, dict) and "propertyId" in result:
                pid = result["propertyId"]
                self.stored_property_id.set(str(pid))
                self.prop_resp.insert(
                    tk.END,
                    f"\n--- Property ID {pid} saved! Auto-filled in Geofence tab. ---",
                )
        except Exception as e:
            self.prop_resp.insert(tk.END, f"ERROR: {e}")

    # ================================================================
    # GEOFENCE TAB
    # ================================================================
    def _build_geofence_tab(self, parent):
        # --- Split: left form (70%) | right preview (30%) ---
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=7)
        container.columnconfigure(1, weight=3)
        container.rowconfigure(0, weight=1)

        # Left side: form
        left_frame = ttk.Frame(container)
        left_frame.grid(row=0, column=0, sticky="nsew")

        # Property ID
        id_frame = ttk.LabelFrame(left_frame, text="Property ID", padding=8)
        id_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(id_frame, text="Property ID (auto-filled from step 1):").pack(side=tk.LEFT)
        ttk.Entry(id_frame, textvariable=self.stored_property_id, width=12).pack(side=tk.LEFT, padx=10)

        # Geofence Info
        info = ttk.LabelFrame(left_frame, text="Geofence Info", padding=8)
        info.pack(fill=tk.X, padx=10, pady=5)

        self.geo_name = tk.StringVar()
        self.geo_address = tk.StringVar()

        ttk.Label(info, text="Geofence Name *:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(info, textvariable=self.geo_name, width=55).grid(row=0, column=1, padx=5, pady=3, sticky="w")

        ttk.Label(info, text="Complete Address:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(info, textvariable=self.geo_address, width=55).grid(row=1, column=1, padx=5, pady=3, sticky="w")

        # Auto-fill address = geofence name
        self.geo_name.trace_add("write", lambda *_: self.geo_address.set(self.geo_name.get()))

        # GeoJSON input
        gj = ttk.LabelFrame(left_frame, text="GeoJSON Input  (paste FeatureCollection from geojson.io)", padding=8)
        gj.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.geojson_input = scrolledtext.ScrolledText(gj, height=14, width=90, font=("Consolas", 9))
        self.geojson_input.pack(fill=tk.BOTH, expand=True)

        # Right side: JSON preview + response
        right_frame = ttk.Frame(container)
        right_frame.grid(row=0, column=1, sticky="nsew")

        btn = ttk.Frame(right_frame)
        btn.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn, text="Preview JSON", command=self._preview_geofence).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Create Geofence", command=self._create_geofence).pack(side=tk.LEFT, padx=5)

        ttk.Label(right_frame, text="JSON Preview / Response:", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=8, pady=(5, 0)
        )
        self.geo_resp = scrolledtext.ScrolledText(right_frame, font=("Consolas", 9), wrap=tk.WORD)
        self.geo_resp.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

    # ---- Convert GeoJSON [lon,lat] -> API {latitude, longitude} (same as 2.py) ----
    def _convert_geojson(self):
        raw = self.geojson_input.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showerror("Error", "Paste GeoJSON data first!")
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            messagebox.showerror("Invalid JSON", str(e))
            return None

        # Accept FeatureCollection, single Feature, or bare Geometry
        if data.get("type") == "FeatureCollection":
            features = data.get("features", [])
        elif data.get("type") == "Feature":
            features = [data]
        elif data.get("type") in ("Polygon", "MultiPolygon"):
            features = [{"geometry": data}]
        else:
            messagebox.showerror("Error", "Unsupported GeoJSON type")
            return None

        if not features:
            messagebox.showerror("Error", "No features found")
            return None

        coords = features[0]["geometry"]["coordinates"][0]
        # GeoJSON = [longitude, latitude] -> convert like 2.py
        return [{"latitude": lat, "longitude": lon} for lon, lat in coords]

    def _build_geofence_payload(self):
        pid = self.stored_property_id.get().strip()
        if not pid:
            messagebox.showerror("Error", "Property ID is required! Create a property first or enter manually.")
            return None

        name = self.geo_name.get().strip()
        if not name:
            messagebox.showerror("Error", "Geofence Name is required!")
            return None

        address = self.geo_address.get().strip() or name

        polygon = self._convert_geojson()
        if not polygon:
            return None

        return {
            "propertyId": int(pid),
            "geofences": [
                {
                    "geofenceName": name,
                    "polygonCoordinates": polygon,
                    "address": {"completeAddress": address},
                    "geoShape": "Polygon",
                }
            ],
        }

    def _preview_geofence(self):
        payload = self._build_geofence_payload()
        if payload:
            self.geo_resp.delete("1.0", tk.END)
            self.geo_resp.insert(tk.END, json.dumps(payload, indent=2))

    def _create_geofence(self):
        payload = self._build_geofence_payload()
        if not payload:
            return

        url = f"{self.base_url.get().rstrip('/')}/v2/fleets/{self.fleet_id.get()}/geofences"
        auth = HTTPBasicAuth(self.username.get(), self.password.get())
        headers = {"Content-Type": "application/json"}

        self.geo_resp.delete("1.0", tk.END)
        self.geo_resp.insert(tk.END, f"POST {url}\n\n")

        try:
            resp = requests.post(url, headers=headers, auth=auth, json=payload, timeout=30)
            try:
                result = resp.json()
            except Exception:
                result = resp.text

            self.geo_resp.insert(
                tk.END,
                f"Status: {resp.status_code}\n\n{json.dumps(result, indent=2) if isinstance(result, dict) else result}",
            )
        except Exception as e:
            self.geo_resp.insert(tk.END, f"ERROR: {e}")

    # ================================================================
    # PREVIEW PROPERTIES TAB
    # ================================================================
    def _build_props_tab(self, parent):
        top = ttk.LabelFrame(parent, text="Fleet Geofence Properties", padding=10)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(top, text="Fetch Properties", command=self._fetch_properties).grid(
            row=0, column=0, pady=3, sticky="w"
        )
        ttk.Button(top, text="Delete Selected", command=self._delete_selected_property).grid(
            row=0, column=1, pady=3, sticky="w", padx=(15, 0)
        )

        self.props_count_label = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.props_count_label, foreground="blue").grid(
            row=0, column=2, columnspan=3, pady=3, sticky="w", padx=(15, 0)
        )

        # --- Resizable pane ---
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # -- Top pane: treeview --
        tree_frame = ttk.Frame(pane)
        pane.add(tree_frame, weight=3)

        columns = ("propertyId", "propertyName", "description", "colourHex", "geofenceCount", "rules", "isDefault")
        self.props_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        col_widths = {
            "propertyId": 80,
            "propertyName": 220,
            "description": 180,
            "colourHex": 80,
            "geofenceCount": 100,
            "rules": 350,
            "isDefault": 70,
        }
        col_labels = {
            "propertyId": "Property ID",
            "propertyName": "Property Name",
            "description": "Description",
            "colourHex": "Colour",
            "geofenceCount": "Geofences #",
            "rules": "Rules",
            "isDefault": "Default?",
        }
        for col in columns:
            self.props_tree.heading(col, text=col_labels.get(col, col))
            self.props_tree.column(col, width=col_widths.get(col, 100), minwidth=50)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.props_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.props_tree.xview)
        self.props_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.props_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Right-click context menu
        self.props_ctx_menu = tk.Menu(self.props_tree, tearoff=0)
        self.props_ctx_menu.add_command(label="Delete Property", command=self._delete_selected_property)
        self.props_tree.bind("<Button-3>", self._props_tree_right_click)

        # -- Bottom pane: raw JSON with search --
        raw_frame = ttk.LabelFrame(pane, text="Raw JSON Response", padding=5)
        pane.add(raw_frame, weight=2)

        search_bar = ttk.Frame(raw_frame)
        search_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(search_bar, text="Search:").pack(side=tk.LEFT)
        self.props_search_var = tk.StringVar()
        ttk.Entry(search_bar, textvariable=self.props_search_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Button(search_bar, text="Find Next", command=lambda: self._search_text(self.props_raw, self.props_search_var)).pack(side=tk.LEFT, padx=2)
        ttk.Button(search_bar, text="Find Prev", command=lambda: self._search_text(self.props_raw, self.props_search_var, backward=True)).pack(side=tk.LEFT, padx=2)
        self.props_search_count = tk.StringVar(value="")
        ttk.Label(search_bar, textvariable=self.props_search_count, foreground="gray").pack(side=tk.LEFT, padx=8)

        self.props_raw = scrolledtext.ScrolledText(raw_frame, height=8, font=("Consolas", 9))
        self.props_raw.pack(fill=tk.BOTH, expand=True)

    def _fetch_properties(self):
        base = self.base_url.get().rstrip("/")
        fleet = self.fleet_id.get()
        url = f"{base}/v2/fleets/{fleet}/geofences/properties"
        auth = HTTPBasicAuth(self.username.get(), self.password.get())

        for item in self.props_tree.get_children():
            self.props_tree.delete(item)
        self.props_raw.delete("1.0", tk.END)
        self.props_count_label.set("Fetching...")

        try:
            resp = requests.get(url, auth=auth, timeout=30)
            try:
                result = resp.json()
            except Exception:
                result = resp.text

            self.props_raw.insert(
                tk.END,
                f"GET {url}\nStatus: {resp.status_code}\n\n"
                f"{json.dumps(result, indent=2) if isinstance(result, (dict, list)) else result}",
            )

            rows = []
            if isinstance(result, dict):
                rows = result.get("rows", [])
            elif isinstance(result, list):
                rows = result

            total_count = result.get("totalCount", len(rows)) if isinstance(result, dict) else len(rows)
            self.props_count_label.set(f"{len(rows)} properties  |  Total: {total_count}  |  Status: {resp.status_code}")

            for prop in rows:
                rules_summary = []
                for r in prop.get("geofenceRules", []):
                    action = r.get("action", "")
                    target = r.get("target", "")
                    applies = r.get("appliesTo", [])
                    extra = ""
                    if applies:
                        extra = f" ({','.join(applies)})"
                    if r.get("farAwayDistanceInKm"):
                        extra = f" ({r['farAwayDistanceInKm']}km)"
                    if r.get("fileType"):
                        extra = f" ({r['fileType']})"
                    if r.get("assetConfiguration"):
                        cfg = r["assetConfiguration"]
                        blur = cfg.get("blurConfig", {})
                        if blur:
                            extra = f" (blur:{blur.get('driverBlurMode', '')})"
                    rules_summary.append(f"{action} {target}{extra}")

                gf_ids = prop.get("geofenceIds", [])
                self.props_tree.insert(
                    "",
                    tk.END,
                    values=(
                        prop.get("propertyId", ""),
                        prop.get("propertyName", ""),
                        prop.get("description", ""),
                        prop.get("colourHex", ""),
                        len(gf_ids),
                        " | ".join(rules_summary),
                        "Yes" if prop.get("isDefaultProperty") else "No",
                    ),
                )

        except Exception as e:
            self.props_count_label.set("Error!")
            self.props_raw.insert(tk.END, f"ERROR: {e}")

    def _props_tree_right_click(self, event):
        item = self.props_tree.identify_row(event.y)
        if item:
            self.props_tree.selection_set(item)
            self.props_ctx_menu.post(event.x_root, event.y_root)

    def _delete_selected_property(self):
        selected = self.props_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a property row first.")
            return

        values = self.props_tree.item(selected[0], "values")
        # columns: propertyId, propertyName, description, colourHex, geofenceCount, rules, isDefault
        property_id = values[0]
        prop_name = values[1]
        gf_count = values[4]

        if not property_id or str(property_id) == "-1":
            messagebox.showerror("Error", "Cannot delete the default property.")
            return

        confirm = messagebox.askquestion(
            "Delete Property",
            f"Are you sure you want to delete?\n\n"
            f"Property: {prop_name}\n"
            f"PropertyId: {property_id}\n"
            f"Geofences linked: {gf_count}\n\n"
            f"This will DELETE the property and all its geofences.",
            icon="warning",
        )
        if confirm != "yes":
            return

        base = self.base_url.get().rstrip("/")
        fleet = self.fleet_id.get()
        url = f"{base}/v2/fleets/{fleet}/geofences/properties/{property_id}"
        auth = HTTPBasicAuth(self.username.get(), self.password.get())

        try:
            resp = requests.delete(url, auth=auth, timeout=30)
            if resp.status_code in (200, 204):
                messagebox.showinfo("Deleted", f"Property {property_id} deleted successfully.")
                self._fetch_properties()
            else:
                try:
                    body = json.dumps(resp.json(), indent=2)
                except Exception:
                    body = resp.text
                messagebox.showerror("Delete Failed", f"Status: {resp.status_code}\n\n{body}")
        except Exception as e:
            messagebox.showerror("Error", f"Request failed:\n{e}")

    # ================================================================
    # PREVIEW DEVICE GEOFENCES TAB
    # ================================================================
    def _build_preview_tab(self, parent):
        # --- Top: inputs ---
        top = ttk.LabelFrame(parent, text="Fetch Device Geofences", padding=10)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top, text="Device ID:").grid(row=0, column=0, sticky="w", pady=3)
        self.preview_device_id = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.preview_device_id, width=30).grid(
            row=0, column=1, padx=5, pady=3, sticky="w"
        )

        ttk.Label(top, text="Limit:").grid(row=0, column=2, sticky="w", padx=(15, 0), pady=3)
        self.preview_limit = tk.StringVar(value="500")
        ttk.Entry(top, textvariable=self.preview_limit, width=8).grid(
            row=0, column=3, padx=5, pady=3, sticky="w"
        )

        ttk.Label(top, text="Status:").grid(row=0, column=4, sticky="w", padx=(15, 0), pady=3)
        self.preview_status = tk.StringVar(value="ACTIVE")
        ttk.Combobox(
            top,
            textvariable=self.preview_status,
            values=["ACTIVE", "INACTIVE", ""],
            width=10,
            state="readonly",
        ).grid(row=0, column=5, padx=5, pady=3, sticky="w")

        ttk.Button(top, text="Fetch Geofences", command=self._fetch_device_geofences).grid(
            row=1, column=0, columnspan=2, pady=(8, 0), sticky="w"
        )
        ttk.Button(top, text="Delete Selected", command=self._delete_selected_geofence).grid(
            row=1, column=2, pady=(8, 0), sticky="w", padx=(15, 0)
        )

        self.preview_count_label = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.preview_count_label, foreground="blue").grid(
            row=1, column=3, columnspan=3, pady=(8, 0), sticky="w"
        )

        # --- Resizable pane: treeview (top) | raw JSON (bottom) ---
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # -- Top pane: treeview table --
        tree_frame = ttk.Frame(pane)
        pane.add(tree_frame, weight=3)

        columns = ("geofenceName", "geofenceId", "polygonId", "propertyId", "status", "rules")
        self.preview_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        col_widths = {
            "geofenceName": 250,
            "geofenceId": 80,
            "polygonId": 80,
            "propertyId": 80,
            "status": 70,
            "rules": 350,
        }
        for col in columns:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=col_widths.get(col, 100), minwidth=50)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.preview_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Right-click context menu
        self.preview_ctx_menu = tk.Menu(self.preview_tree, tearoff=0)
        self.preview_ctx_menu.add_command(label="Delete Geofence Property", command=self._delete_selected_geofence)
        self.preview_tree.bind("<Button-3>", self._preview_tree_right_click)

        # -- Bottom pane: raw JSON response with search --
        raw_frame = ttk.LabelFrame(pane, text="Raw JSON Response", padding=5)
        pane.add(raw_frame, weight=2)

        # Search bar
        search_bar = ttk.Frame(raw_frame)
        search_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(search_bar, text="Search:").pack(side=tk.LEFT)
        self.preview_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_bar, textvariable=self.preview_search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(search_bar, text="Find Next", command=lambda: self._search_text(self.preview_raw, self.preview_search_var)).pack(side=tk.LEFT, padx=2)
        ttk.Button(search_bar, text="Find Prev", command=lambda: self._search_text(self.preview_raw, self.preview_search_var, backward=True)).pack(side=tk.LEFT, padx=2)
        self.preview_search_count = tk.StringVar(value="")
        ttk.Label(search_bar, textvariable=self.preview_search_count, foreground="gray").pack(side=tk.LEFT, padx=8)

        self.preview_raw = scrolledtext.ScrolledText(raw_frame, height=8, font=("Consolas", 9))
        self.preview_raw.pack(fill=tk.BOTH, expand=True)

    def _fetch_device_geofences(self):
        device_id = self.preview_device_id.get().strip()
        if not device_id:
            messagebox.showerror("Error", "Device ID is required!")
            return

        base = self.base_url.get().rstrip("/")
        fleet = self.fleet_id.get()
        url = f"{base}/v2/fleets/{fleet}/geofences/devices/{device_id}"

        params = {}
        limit = self.preview_limit.get().strip()
        if limit:
            params["limit"] = limit
        status = self.preview_status.get().strip()
        if status:
            params["status"] = status

        auth = HTTPBasicAuth(self.username.get(), self.password.get())

        # Clear previous
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.preview_raw.delete("1.0", tk.END)
        self.preview_count_label.set("Fetching...")

        try:
            resp = requests.get(url, params=params, auth=auth, timeout=30)
            try:
                result = resp.json()
            except Exception:
                result = resp.text

            # Show raw JSON
            self.preview_raw.insert(
                tk.END,
                f"GET {url}?{('&'.join(f'{k}={v}' for k, v in params.items()))}\n"
                f"Status: {resp.status_code}\n\n"
                f"{json.dumps(result, indent=2) if isinstance(result, (dict, list)) else result}",
            )

            # Parse rows into table
            rows = []
            if isinstance(result, dict):
                rows = result.get("rows", [])
            elif isinstance(result, list):
                rows = result

            self.preview_count_label.set(f"{len(rows)} geofences found  |  Status: {resp.status_code}")

            for gf in rows:
                rules_summary = []
                for r in gf.get("rules", []):
                    action = r.get("action", "")
                    target = r.get("target", "")
                    applies = r.get("appliesTo", [])
                    extra = ""
                    if applies:
                        extra = f" ({','.join(applies)})"
                    if r.get("farAwayDistanceInKm"):
                        extra = f" ({r['farAwayDistanceInKm']}km)"
                    if r.get("fileType"):
                        extra = f" ({r['fileType']})"
                    if r.get("assetConfiguration"):
                        cfg = r["assetConfiguration"]
                        blur = cfg.get("blurConfig", {})
                        if blur:
                            extra = f" (blur:{blur.get('driverBlurMode', '')})"
                    rules_summary.append(f"{action} {target}{extra}")

                self.preview_tree.insert(
                    "",
                    tk.END,
                    values=(
                        gf.get("geofenceName", ""),
                        gf.get("geofenceId", ""),
                        gf.get("polygonId", ""),
                        gf.get("propertyId", ""),
                        gf.get("status", ""),
                        " | ".join(rules_summary),
                    ),
                )

        except Exception as e:
            self.preview_count_label.set("Error!")
            self.preview_raw.insert(tk.END, f"ERROR: {e}")

    def _preview_tree_right_click(self, event):
        item = self.preview_tree.identify_row(event.y)
        if item:
            self.preview_tree.selection_set(item)
            self.preview_ctx_menu.post(event.x_root, event.y_root)

    def _delete_selected_geofence(self):
        selected = self.preview_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a geofence row first.")
            return

        values = self.preview_tree.item(selected[0], "values")
        # columns: geofenceName, geofenceId, polygonId, propertyId, status, rules
        gf_name = values[0]
        gf_id = values[1]
        property_id = values[3]

        if not property_id:
            messagebox.showerror("Error", "No propertyId found for this geofence.")
            return

        confirm = messagebox.askquestion(
            "Delete Geofence Property",
            f"Are you sure you want to delete?\n\n"
            f"Geofence: {gf_name}\n"
            f"GeofenceId: {gf_id}\n"
            f"PropertyId: {property_id}\n\n"
            f"This will DELETE the property and all its geofences.",
            icon="warning",
        )
        if confirm != "yes":
            return

        base = self.base_url.get().rstrip("/")
        fleet = self.fleet_id.get()
        url = f"{base}/v2/fleets/{fleet}/geofences/properties/{property_id}"
        auth = HTTPBasicAuth(self.username.get(), self.password.get())

        try:
            resp = requests.delete(url, auth=auth, timeout=30)
            if resp.status_code in (200, 204):
                messagebox.showinfo("Deleted", f"Property {property_id} deleted successfully.")
                # Refresh the list
                self._fetch_device_geofences()
            else:
                try:
                    body = json.dumps(resp.json(), indent=2)
                except Exception:
                    body = resp.text
                messagebox.showerror(
                    "Delete Failed",
                    f"Status: {resp.status_code}\n\n{body}",
                )
        except Exception as e:
            messagebox.showerror("Error", f"Request failed:\n{e}")

    # ================================================================
    # ACTIVITY TAB
    # ================================================================
    def _build_activity_tab(self, parent):
        # --- Top: inputs ---
        top = ttk.LabelFrame(parent, text="Fetch Geofence Activities", padding=10)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top, text="Skip:").grid(row=0, column=0, sticky="w", pady=3)
        self.activity_skip = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.activity_skip, width=8).grid(
            row=0, column=1, padx=5, pady=3, sticky="w"
        )

        ttk.Label(top, text="Limit:").grid(row=0, column=2, sticky="w", padx=(15, 0), pady=3)
        self.activity_limit = tk.StringVar(value="50")
        ttk.Entry(top, textvariable=self.activity_limit, width=8).grid(
            row=0, column=3, padx=5, pady=3, sticky="w"
        )

        ttk.Button(top, text="Fetch Activities", command=self._fetch_activities).grid(
            row=1, column=0, columnspan=2, pady=(8, 0), sticky="w"
        )

        self.activity_count_label = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.activity_count_label, foreground="blue").grid(
            row=1, column=2, columnspan=4, pady=(8, 0), sticky="w"
        )

        # --- Resizable pane: treeview (top) | raw JSON (bottom) ---
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # -- Top pane: treeview table --
        tree_frame = ttk.Frame(pane)
        pane.add(tree_frame, weight=3)

        columns = (
            "timestampUTC", "geofenceActivity", "geofenceName",
            "geofenceId", "propertyId", "assetId", "driverId",
        )
        self.activity_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        col_widths = {
            "timestampUTC": 170,
            "geofenceActivity": 130,
            "geofenceName": 200,
            "geofenceId": 80,
            "propertyId": 80,
            "assetId": 150,
            "driverId": 150,
        }
        for col in columns:
            self.activity_tree.heading(col, text=col)
            self.activity_tree.column(col, width=col_widths.get(col, 100), minwidth=50)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.activity_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.activity_tree.xview)
        self.activity_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.activity_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # -- Bottom pane: raw JSON response with search --
        raw_frame = ttk.LabelFrame(pane, text="Raw JSON Response", padding=5)
        pane.add(raw_frame, weight=2)

        # Search bar
        search_bar = ttk.Frame(raw_frame)
        search_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(search_bar, text="Search:").pack(side=tk.LEFT)
        self.activity_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_bar, textvariable=self.activity_search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(search_bar, text="Find Next", command=lambda: self._search_text(self.activity_raw, self.activity_search_var)).pack(side=tk.LEFT, padx=2)
        ttk.Button(search_bar, text="Find Prev", command=lambda: self._search_text(self.activity_raw, self.activity_search_var, backward=True)).pack(side=tk.LEFT, padx=2)
        self.activity_search_count = tk.StringVar(value="")
        ttk.Label(search_bar, textvariable=self.activity_search_count, foreground="gray").pack(side=tk.LEFT, padx=8)

        self.activity_raw = scrolledtext.ScrolledText(raw_frame, height=8, font=("Consolas", 9))
        self.activity_raw.pack(fill=tk.BOTH, expand=True)

    def _fetch_activities(self):
        base = self.base_url.get().rstrip("/")
        fleet = self.fleet_id.get()
        url = f"{base}/v2/fleets/{fleet}/geofences/activities"

        params = {}
        skip = self.activity_skip.get().strip()
        if skip:
            params["skip"] = skip
        limit = self.activity_limit.get().strip()
        if limit:
            params["limit"] = limit

        auth = HTTPBasicAuth(self.username.get(), self.password.get())

        # Clear previous
        for item in self.activity_tree.get_children():
            self.activity_tree.delete(item)
        self.activity_raw.delete("1.0", tk.END)
        self.activity_count_label.set("Fetching...")

        try:
            resp = requests.get(url, params=params, auth=auth, timeout=30)
            try:
                result = resp.json()
            except Exception:
                result = resp.text

            # Show raw JSON
            self.activity_raw.insert(
                tk.END,
                f"GET {url}?{('&'.join(f'{k}={v}' for k, v in params.items()))}\n"
                f"Status: {resp.status_code}\n\n"
                f"{json.dumps(result, indent=2) if isinstance(result, (dict, list)) else result}",
            )

            # Parse rows into table
            rows = []
            total_count = ""
            if isinstance(result, dict):
                rows = result.get("rows", [])
                total_count = result.get("totalCount", "")
            elif isinstance(result, list):
                rows = result

            info = f"{len(rows)} activities shown"
            if total_count:
                info += f"  |  Total: {total_count}"
            info += f"  |  Status: {resp.status_code}"
            self.activity_count_label.set(info)

            for act in rows:
                # For GeofenceUpdate type, show userInfo instead of assetId/driverId
                asset_id = act.get("assetId", "")
                driver_id = act.get("driverId", "")
                user_info = act.get("userInfo")
                if user_info and not asset_id:
                    asset_id = f"user:{user_info.get('loginId', '')}"
                    driver_id = user_info.get("email", "")

                self.activity_tree.insert(
                    "",
                    tk.END,
                    values=(
                        act.get("timestampUTC", ""),
                        act.get("geofenceActivity", ""),
                        act.get("geofenceName", ""),
                        act.get("geofenceId", ""),
                        act.get("propertyId", ""),
                        asset_id,
                        driver_id,
                    ),
                )

        except Exception as e:
            self.activity_count_label.set("Error!")
            self.activity_raw.insert(tk.END, f"ERROR: {e}")

    # ================================================================
    # SHARED: Search in ScrolledText widget
    # ================================================================
    def _search_text(self, text_widget, search_var, backward=False):
        term = search_var.get()
        text_widget.tag_remove("search_hl", "1.0", tk.END)
        if not term:
            return

        # Count total matches
        count_var = tk.IntVar()
        start = "1.0"
        total = 0
        while True:
            pos = text_widget.search(term, start, stopindex=tk.END, nocase=True, count=count_var)
            if not pos:
                break
            total += 1
            end = f"{pos}+{count_var.get()}c"
            text_widget.tag_add("search_hl", pos, end)
            start = end
        text_widget.tag_configure("search_hl", background="yellow", foreground="black")

        # Determine which status label to update
        if text_widget is self.preview_raw:
            status_var = self.preview_search_count
        elif text_widget is self.activity_raw:
            status_var = self.activity_search_count
        elif text_widget is self.props_raw:
            status_var = self.props_search_count
        else:
            status_var = None

        if total == 0:
            if status_var:
                status_var.set("No matches")
            return

        if status_var:
            status_var.set(f"{total} matches")

        # Navigate to next/prev match from current cursor
        current = text_widget.index(tk.INSERT)
        if backward:
            pos = text_widget.search(term, current, stopindex="1.0", nocase=True, backwards=True, count=count_var)
            if not pos:
                pos = text_widget.search(term, tk.END, stopindex="1.0", nocase=True, backwards=True, count=count_var)
        else:
            pos = text_widget.search(term, f"{current}+1c", stopindex=tk.END, nocase=True, count=count_var)
            if not pos:
                pos = text_widget.search(term, "1.0", stopindex=tk.END, nocase=True, count=count_var)

        if pos:
            text_widget.mark_set(tk.INSERT, pos)
            text_widget.see(pos)
            end = f"{pos}+{count_var.get()}c"
            text_widget.tag_remove("search_current", "1.0", tk.END)
            text_widget.tag_add("search_current", pos, end)
            text_widget.tag_configure("search_current", background="orange", foreground="black")

    # ================================================================
    # MAP PREVIEW TAB
    # ================================================================
    MAP_COLORS = [
        "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
        "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
        "#dcbeff", "#9A6324", "#800000", "#aaffc3", "#808000",
        "#ffd8b1", "#000075", "#a9a9a9", "#e6beff", "#fffac8",
    ]

    def _build_map_tab(self, parent):
        top = ttk.LabelFrame(parent, text="Visualize Device Geofences on Map", padding=10)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top, text="Device ID:").grid(row=0, column=0, sticky="w", pady=3)
        self.map_device_id = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.map_device_id, width=30).grid(
            row=0, column=1, padx=5, pady=3, sticky="w"
        )

        ttk.Label(top, text="Status:").grid(row=0, column=2, sticky="w", padx=(15, 0), pady=3)
        self.map_status = tk.StringVar(value="ACTIVE")
        ttk.Combobox(
            top, textvariable=self.map_status,
            values=["ACTIVE", "INACTIVE", ""], width=10, state="readonly",
        ).grid(row=0, column=3, padx=5, pady=3, sticky="w")

        ttk.Label(top, text="Workers:").grid(row=0, column=4, sticky="w", padx=(15, 0), pady=3)
        self.map_workers = tk.StringVar(value="30")
        ttk.Entry(top, textvariable=self.map_workers, width=5).grid(
            row=0, column=5, padx=5, pady=3, sticky="w"
        )

        ttk.Button(top, text="Generate Map & Open in Browser", command=self._generate_map).grid(
            row=1, column=0, columnspan=3, pady=(8, 0), sticky="w"
        )

        self.map_status_label = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.map_status_label, foreground="blue").grid(
            row=1, column=3, columnspan=3, pady=(8, 0), sticky="w"
        )

        # Log area
        log_frame = ttk.LabelFrame(parent, text="Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.map_log = scrolledtext.ScrolledText(log_frame, height=20, font=("Consolas", 9))
        self.map_log.pack(fill=tk.BOTH, expand=True)

    def _generate_map(self):
        device_id = self.map_device_id.get().strip()
        if not device_id:
            messagebox.showerror("Error", "Device ID is required!")
            return

        self.map_log.delete("1.0", tk.END)
        self.map_status_label.set("Working...")

        # Run in background thread so GUI stays responsive
        threading.Thread(target=self._map_worker, args=(device_id,), daemon=True).start()

    def _map_log_append(self, text):
        self.root.after(0, lambda: self.map_log.insert(tk.END, text + "\n"))

    def _map_worker(self, device_id):
        try:
            base = self.base_url.get().rstrip("/")
            fleet = self.fleet_id.get()
            auth = HTTPBasicAuth(self.username.get(), self.password.get())
            max_workers = int(self.map_workers.get() or 30)

            # Step 1: fetch device geofences
            url = f"{base}/v2/fleets/{fleet}/geofences/devices/{device_id}"
            params = {"limit": 500}
            status_filter = self.map_status.get().strip()
            if status_filter:
                params["status"] = status_filter

            self._map_log_append(f"[1/3] Fetching geofences...\n  GET {url}")
            resp = requests.get(url, params=params, auth=auth, timeout=30)
            resp.raise_for_status()
            geofences = resp.json().get("rows", [])
            self._map_log_append(f"  -> {len(geofences)} geofences found.")

            if not geofences:
                self.root.after(0, lambda: self.map_status_label.set("No geofences found."))
                return

            # Step 2: fetch polygon coordinates in parallel
            self._map_log_append(f"\n[2/3] Fetching {len(geofences)} polygon shapes ({max_workers} parallel)...")
            polygon_coords = {}
            done = [0]

            def fetch_one(gf):
                pid = gf.get("polygonId")
                if pid is None:
                    return pid, None
                poly_url = f"{base}/v1/fleets/{fleet}/geofences/polygons/{pid}"
                try:
                    r = requests.get(poly_url, auth=auth, timeout=30)
                    r.raise_for_status()
                    raw = r.json()
                    inner = raw.get("rows", raw)
                    coords = inner.get("coordinates", [])
                    return pid, [(c["latitude"], c["longitude"]) for c in coords]
                except Exception as e:
                    self._map_log_append(f"  ! polygon {pid} failed: {e}")
                    return pid, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(fetch_one, gf): gf for gf in geofences}
                for fut in concurrent.futures.as_completed(futures):
                    pid, coords = fut.result()
                    if coords:
                        polygon_coords[pid] = coords
                    done[0] += 1
                    if done[0] % 10 == 0 or done[0] == len(geofences):
                        self._map_log_append(f"  {done[0]}/{len(geofences)}")

            self._map_log_append(f"  -> {len(polygon_coords)} polygons with coordinates ready.")

            # Step 3: build HTML and open
            self._map_log_append("\n[3/3] Building map...")
            html = self._build_map_html(geofences, polygon_coords, fleet, device_id)

            out_path = os.path.join(tempfile.gettempdir(), "geofence_map_preview.html")
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(html)

            self._map_log_append(f"\n  Map saved -> {out_path}")
            self._map_log_append("  Opening in browser...")
            webbrowser.open(f"file:///{out_path.replace(os.sep, '/')}")

            self.root.after(0, lambda: self.map_status_label.set(
                f"Done! {len(polygon_coords)} polygons rendered."
            ))

        except Exception as e:
            self._map_log_append(f"\nERROR: {e}")
            self.root.after(0, lambda: self.map_status_label.set("Error!"))

    def _build_map_html(self, geofences, polygon_coords, fleet, device_id):
        all_lats = [lat for coords in polygon_coords.values() for lat, _ in coords]
        all_lons = [lon for coords in polygon_coords.values() for _, lon in coords]

        if not all_lats:
            center_lat, center_lon, zoom = 20.0, 0.0, 2
        else:
            center_lat = (min(all_lats) + max(all_lats)) / 2
            center_lon = (min(all_lons) + max(all_lons)) / 2
            span = max(max(all_lats) - min(all_lats), max(all_lons) - min(all_lons))
            zoom = max(2, min(14, int(math.log2(360 / span)) if span > 0 else 6))

        pid_to_gf = {gf["polygonId"]: gf for gf in geofences if "polygonId" in gf}

        # Bounding boxes per polygon
        all_bboxes = []
        for coords in polygon_coords.values():
            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]
            mn_lat, mx_lat = min(lats), max(lats)
            mn_lon, mx_lon = min(lons), max(lons)
            all_bboxes.append([
                [mn_lat, mn_lon], [mn_lat, mx_lon],
                [mx_lat, mx_lon], [mx_lat, mn_lon],
                [mn_lat, mn_lon],
            ])

        # Polygon layers with popups
        poly_layers = []
        for idx, (pid, coords) in enumerate(polygon_coords.items()):
            color = self.MAP_COLORS[idx % len(self.MAP_COLORS)]
            gf = pid_to_gf.get(pid, {})
            name = gf.get("geofenceName", f"Polygon {pid}")

            rules_html = "<br>".join(
                "<b>{}</b> -> {}{}".format(
                    r.get("action", ""),
                    r.get("target", ""),
                    " ({})".format(", ".join(r.get("appliesTo", []))) if r.get("appliesTo") else ""
                )
                for r in gf.get("rules", [])
            )

            popup = (
                "<b>{}</b><br>"
                "GeofenceId: {} | PolygonId: {}<br>"
                "PropertyId: {}<br>"
                "Status: {}<br>"
                "Rules:<br>{}"
            ).format(
                name,
                gf.get("geofenceId", ""), pid,
                gf.get("propertyId", ""),
                gf.get("status", ""),
                rules_html,
            )

            latlngs = json.dumps([[lat, lon] for lat, lon in coords])
            poly_layers.append(
                "L.polygon({},{{color:'{}',weight:2,fillOpacity:0.25}}).addTo(map).bindPopup({});".format(
                    latlngs, color, json.dumps(popup)
                )
            )

        return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Fleet Geofence Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    #map {{ height:100vh; width:100vw; }}
    #info {{
      position:absolute; top:10px; left:60px; z-index:1000;
      background:rgba(255,255,255,0.93); padding:10px 16px;
      border-radius:8px; font-family:sans-serif; font-size:13px;
      box-shadow:0 2px 8px rgba(0,0,0,0.25);
    }}
    #legend {{
      position:absolute; bottom:30px; right:10px; z-index:1000;
      background:rgba(255,255,255,0.93); padding:8px 12px;
      border-radius:8px; font-family:sans-serif; font-size:12px;
      box-shadow:0 2px 8px rgba(0,0,0,0.2);
    }}
    .leg-item {{ display:flex; align-items:center; gap:6px; margin:3px 0; }}
    .leg-swatch {{ width:20px; height:4px; }}
  </style>
</head>
<body>
<div id="map"></div>
<div id="info">
  <b>Fleet: {fleet}</b><br>
  Device: {device}<br>
  {count} active geofences<br>
  <small>Click any polygon for details</small>
</div>
<div id="legend">
  <div class="leg-item"><div class="leg-swatch" style="border:2px dashed #0055ff"></div> Bounding box</div>
  <div class="leg-item"><div class="leg-swatch" style="background:#e6194b"></div> Geofence polygon</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var map = L.map('map').setView([{clat}, {clon}], {zoom});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{
  maxZoom:19, attribution:'Map data \\u00a9 OpenStreetMap contributors'
}}).addTo(map);

// Bounding boxes (dashed blue)
var bboxes = {bboxes};
bboxes.forEach(function(b){{
  L.polygon(b,{{color:'#0055ff',weight:1.5,dashArray:'6,5',fill:false}}).addTo(map);
}});

// Geofence polygons
{polys}
</script>
</body>
</html>""".format(
            fleet=fleet,
            device=device_id,
            count=len(polygon_coords),
            clat=round(center_lat, 6),
            clon=round(center_lon, 6),
            zoom=zoom,
            bboxes=json.dumps(all_bboxes),
            polys="\n".join(poly_layers),
        )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    GeofenceCreatorGUI(root)
    root.mainloop()
