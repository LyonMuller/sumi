"""CustomTkinter interface. Session logic lives in ``controller.py``."""
from __future__ import annotations
from typing import Callable
import tkinter as tk
from PIL import Image, ImageTk
import customtkinter as ctk
import cv2
from .controller import Controller, ViewState, RESOLUTIONS, HOLD_TIMES, LEAVE_DELAYS
from .hotkey import RestoreHotkey
from .theme import apply_theme, COLORS
from .gesture_guides import illustration_size
from .branding import set_process_identity, set_window_icon
from .paths import resource_root
from .system import is_macos, open_path, ui_font_family

FONT = ui_font_family()


def set_text(variable: tk.Variable, value: object) -> None:
    if variable.get() != value:
        variable.set(value)


class App:
    def __init__(self, root: tk.Tk, controller: Controller | None = None) -> None:
        self.root = root
        self.controller = controller or Controller()
        self.image: ImageTk.PhotoImage | None = None
        self.preview_revision = -1
        self.controls_state: tuple[object, ...] | None = None
        self.wrap_width = -1
        self.last_progress = -1.0
        self.guide_key = ''
        self.guide_image: ctk.CTkImage | None = None
        self.help_window: ctk.CTkToplevel | None = None
        self.closing = False
        self.syncing = False
        self.hotkey = RestoreHotkey()
        self.settings_visible = False
        state = self.controller.tick()
        self.camera = tk.StringVar(value=state.camera)
        self.effect = tk.StringVar(value=state.effect)
        self.resolution = tk.StringVar(value=state.resolution)
        self.hold = tk.StringVar(value=state.hold)
        self.backend = tk.StringVar(value=state.output)
        self.leave_enabled = tk.BooleanVar(value=False)
        self.leave_delay = tk.StringVar(value=state.leave_delay)
        root.title('Sumi')
        set_window_icon(root)
        root.geometry('1080x790')
        root.minsize(860, 700)
        apply_theme(root)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        font = (FONT, 13)
        c = COLORS
        header = ctk.CTkFrame(root, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=30, pady=(22, 18))
        header.columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text='Sumi', font=(FONT, 23, 'bold'), text_color=c['text']).grid(row=0, column=0, sticky='w')
        self.state_text = tk.StringVar(value=state.phase_label)
        ctk.CTkLabel(header, textvariable=self.state_text, font=font, text_color=c['muted']).grid(row=0, column=1, sticky='e', padx=20)
        ctk.CTkButton(header, text='Configurar', command=self.toggle_settings, width=116, height=38, corner_radius=19,
            fg_color=c['panel'], hover_color='#e5e8ef', text_color=c['text'], font=font).grid(row=0, column=2)
        self.center = ctk.CTkFrame(root, fg_color='transparent')
        self.center.grid(row=1, column=0, sticky='nsew', padx=28)
        self.center.columnconfigure(0, weight=1)
        self.center.rowconfigure(0, weight=1)
        preview_frame = ctk.CTkFrame(self.center, fg_color=c['preview'], corner_radius=24)
        preview_frame.grid(row=0, column=0, sticky='nsew')
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.preview = tk.Label(preview_frame, text='Sua câmera aparece aqui\n\nClique em Iniciar câmera para começar.',
            font=(FONT, 17), fg='#c8cfdd', bg=c['preview'], anchor='center', width=1, height=1, borderwidth=0)
        self.preview.grid(row=0, column=0, sticky='nsew', padx=14, pady=14)
        badge = ctk.CTkFrame(preview_frame, fg_color='#242b38', corner_radius=15)
        badge.place(x=18, y=18)
        ctk.CTkLabel(badge, textvariable=self.camera, font=(FONT, 12), text_color='#d6dce7').pack(padx=12, pady=3)
        self.step_text = tk.StringVar(value=state.step)
        self.step_label = ctk.CTkLabel(self.center, textvariable=self.step_text, font=font, text_color=c['muted'], wraplength=850)
        self.step_label.grid(row=1, column=0, sticky='ew', pady=(12, 2))
        self.hint = tk.StringVar(value='')
        guide_panel = ctk.CTkFrame(self.center, fg_color='transparent')
        guide_panel.grid(row=2, column=0, sticky='ew', pady=(6, 2))
        guide_panel.columnconfigure(1, weight=1)
        self.guide_icon = ctk.CTkLabel(guide_panel, text='', width=64, height=64)
        self.guide_title = tk.StringVar()
        self.guide_instruction = tk.StringVar()
        ctk.CTkLabel(guide_panel, textvariable=self.guide_title, font=(FONT, 13, 'bold'), text_color=c['text'], anchor='w').grid(row=0, column=1, sticky='w')
        self.guide_label = ctk.CTkLabel(guide_panel, textvariable=self.guide_instruction, font=(FONT, 12), text_color=c['muted'], anchor='w', justify='left', wraplength=680)
        self.guide_label.grid(row=1, column=1, sticky='ew')
        ctk.CTkButton(guide_panel, text='Como fazer', command=self.show_gesture_help, width=96, height=32, corner_radius=16,
            fg_color=c['surface'], hover_color=c['line'], text_color=c['text'], font=(FONT, 12)).grid(row=0, column=2, rowspan=2, sticky='e', padx=(14, 0))
        self.hint_label = ctk.CTkLabel(self.center, textvariable=self.hint, font=(FONT, 12), text_color=c['muted'], height=18, wraplength=850)
        self.hint_label.grid(row=3, column=0, sticky='ew')
        self.progress = ctk.CTkProgressBar(self.center, height=3, corner_radius=2, fg_color=c['surface'], progress_color=c['accent'])
        self.progress.set(0)
        self.progress.grid(row=4, column=0, sticky='ew', padx=200, pady=(4, 4))
        bar = ctk.CTkFrame(root, fg_color='transparent')
        bar.grid(row=2, column=0, sticky='ew', padx=30, pady=(10, 12))
        bar.columnconfigure(1, weight=1)
        effects = ctk.CTkFrame(bar, fg_color='transparent')
        effects.grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(effects, text='Efeito', font=(FONT, 12), text_color=c['muted']).pack(side='left', padx=(0, 10))
        effect_combo = ctk.CTkComboBox(effects, variable=self.effect, values=state.effects, state='readonly', command=self.controller.set_effect,
            width=205, height=36, corner_radius=12, border_width=0, fg_color=c['panel'], button_color=c['panel'], button_hover_color=c['surface'], text_color=c['text'], font=font)
        effect_combo.pack(side='left')
        modes = ctk.CTkFrame(bar, fg_color='transparent')
        modes.grid(row=0, column=2, sticky='e')
        ctk.CTkLabel(modes, text='Fundo', font=(FONT, 12), text_color=c['muted']).pack(side='left', padx=(0, 10))
        self.background_mode = tk.StringVar(value='Em movimento' if state.dynamic_background else 'Estático')
        self.background_selector = ctk.CTkSegmentedButton(modes, values=['Estático', 'Em movimento'], variable=self.background_mode,
            command=lambda value: self.controller.set_background(value == 'Em movimento'), height=36, corner_radius=12, border_width=3,
            fg_color=c['surface'], unselected_color=c['surface'], unselected_hover_color='#dce1e9', selected_color='#dce0ff',
            selected_hover_color='#cdd3fa', text_color=c['text'], font=font)
        self.background_selector.pack(side='left')
        actions = ctk.CTkFrame(root, fg_color='transparent')
        actions.grid(row=3, column=0, sticky='ew', padx=30, pady=(0, 8))
        actions.columnconfigure((0, 2), weight=1)
        self.primary = ctk.CTkButton(actions, text='Iniciar câmera', command=self.controller.primary_action, state='disabled', height=48, width=252, corner_radius=24,
            fg_color=c['accent'], hover_color=c['accent_hover'], text_color='#ffffff', font=(FONT, 15, 'bold'))
        self.primary.grid(row=0, column=1)
        ctk.CTkButton(actions, text='Restaurar · F8', command=lambda: self.controller.command('restore'), height=36, width=126, corner_radius=18,
            fg_color='transparent', hover_color=c['surface'], text_color=c['muted'], font=font).grid(row=0, column=2, sticky='e')
        self.main_meet_notice = tk.StringVar(value='')
        ctk.CTkLabel(root, textvariable=self.main_meet_notice, text_color=c['danger'], font=(FONT, 12), height=18).grid(row=4, column=0, sticky='ew')
        footer = ctk.CTkFrame(root, fg_color='transparent')
        footer.grid(row=5, column=0, sticky='ew', padx=30, pady=(0, 12))
        footer.columnconfigure(0, weight=1)
        self.shortcut = tk.StringVar(value='Processamento local')
        ctk.CTkLabel(footer, textvariable=self.shortcut, font=(FONT, 11), text_color=c['muted']).grid(row=0, column=0, sticky='w')
        self.performance = tk.StringVar(value=state.performance)
        ctk.CTkLabel(footer, textvariable=self.performance, font=(FONT, 11), text_color=c['muted']).grid(row=0, column=1, sticky='e')
        self.settings_window = ctk.CTkFrame(root, width=410, height=570, corner_radius=22, fg_color=c['panel'], border_width=1, border_color=c['line'])
        self.settings_window.pack_propagate(False)
        panel_header = ctk.CTkFrame(self.settings_window, fg_color='transparent')
        panel_header.pack(fill='x', padx=22, pady=(16, 0))
        ctk.CTkLabel(panel_header, text='Configurar', font=(FONT, 19, 'bold'), text_color=c['text']).pack(side='left')
        ctk.CTkButton(panel_header, text='Fechar', width=64, height=30, corner_radius=15, fg_color=c['surface'], text_color=c['text'], hover_color=c['line'], command=self.toggle_settings).pack(side='right')
        self.tabs = ctk.CTkTabview(self.settings_window, corner_radius=16, fg_color=c['panel'], segmented_button_selected_color=c['accent'], segmented_button_selected_hover_color=c['accent_hover'])
        self.tabs.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        camera_tab = self.tabs.add('Câmera')
        meet_tab = self.tabs.add('Meet')
        self.config = ctk.CTkScrollableFrame(camera_tab, fg_color='transparent')
        self.config.pack(fill='both', expand=True)
        self.config.columnconfigure(0, weight=1)

        def label(parent: ctk.CTkFrame, text: str, row: int) -> None:
            ctk.CTkLabel(parent, text=text, text_color=c['muted'], font=font, anchor='w').grid(row=row, column=0, sticky='w', pady=(12, 5))

        def combo(parent: ctk.CTkFrame, variable: tk.StringVar, values: list[str], row: int,
                  setter: Callable[[str], None]) -> ctk.CTkComboBox:
            widget = ctk.CTkComboBox(parent, variable=variable, values=values, state='readonly', height=38, corner_radius=10,
                border_color=c['line'], fg_color='#ffffff', button_color=c['surface'], button_hover_color=c['line'], text_color=c['text'], font=font,
                command=lambda value: self.apply(setter, value))
            widget.grid(row=row, column=0, sticky='ew')
            return widget
        label(self.config, 'Webcam', 0)
        self.camera_combo = combo(self.config, self.camera, [], 1, self.controller.set_camera)
        self.camera_combo.configure(state='disabled')
        self.refresh_button = ctk.CTkButton(self.config, text='Atualizar lista', command=self.controller.refresh_devices, height=32, corner_radius=10,
            fg_color=c['surface'], hover_color=c['line'], text_color=c['text'], font=font)
        self.refresh_button.grid(row=2, column=0, sticky='w', pady=(8, 0))
        self.start_button = ctk.CTkButton(self.config, text='Iniciar câmera', command=self.controller.start, state='disabled', height=36, corner_radius=10,
            fg_color=c['accent'], hover_color=c['accent_hover'], font=font)
        self.start_button.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        label(self.config, 'Qualidade', 4)
        resolution_combo = combo(self.config, self.resolution, list(RESOLUTIONS), 5, self.controller.set_resolution)
        label(self.config, 'Duração das poses (estalo e pinça usam movimento)', 6)
        hold_combo = combo(self.config, self.hold, list(HOLD_TIMES), 7, self.controller.set_hold)
        self.recalibrate = ctk.CTkButton(self.config, text='Capturar fundo novamente', command=lambda: self.controller.command('calibrate'), state='disabled',
            height=36, corner_radius=10, fg_color=c['surface'], hover_color=c['line'], text_color=c['text'], font=font)
        self.recalibrate.grid(row=8, column=0, sticky='ew', pady=(18, 8))
        self.background_description = tk.StringVar(value=state.background_description)
        ctk.CTkLabel(self.config, textvariable=self.background_description, wraplength=315, text_color=c['muted'], font=(FONT, 12), justify='left').grid(row=9, column=0, sticky='w')
        self.status = tk.StringVar(value=state.status)
        self.status_label = ctk.CTkLabel(self.config, textvariable=self.status, wraplength=315, justify='left', text_color=c['muted'], font=(FONT, 12))
        self.status_label.grid(row=10, column=0, sticky='ew', pady=(14, 0))
        self.right = ctk.CTkScrollableFrame(meet_tab, fg_color='transparent')
        self.right.pack(fill='both', expand=True)
        self.right.columnconfigure(0, weight=1)
        label(self.right, 'Câmera enviada à chamada', 0)
        backend_combo = combo(self.right, self.backend, state.outputs, 1, self.controller.set_output)
        self.output_help = tk.StringVar(value=state.output_help)
        ctk.CTkLabel(self.right, textvariable=self.output_help, wraplength=315,
            text_color=c['muted'], font=font, justify='left').grid(row=2, column=0, sticky='w', pady=10)
        ctk.CTkButton(self.right, text='Preparar vídeo para o Meet', command=self.controller.prepare_meet, height=36, corner_radius=10,
            fg_color=c['accent'], hover_color=c['accent_hover'], font=font).grid(row=3, column=0, sticky='ew')
        ctk.CTkButton(self.right, text='Reconectar saída', command=lambda: self.controller.command('virtual'), height=32, corner_radius=10,
            fg_color=c['surface'], hover_color=c['line'], text_color=c['text'], font=font).grid(row=4, column=0, sticky='w', pady=(8, 14))
        self.leave_toggle = ctk.CTkSwitch(self.right, text='Sair do Meet após desaparecer', variable=self.leave_enabled,
            command=lambda: self.controller.set_leave(self.leave_enabled.get()), progress_color=c['accent'], text_color=c['text'], font=font)
        self.leave_toggle.grid(row=5, column=0, sticky='w', pady=(8, 8))
        ctk.CTkLabel(self.right, text='Opcional. Requer a extensão e fecha apenas a aba vinculada.', text_color=c['muted'], font=(FONT, 12), wraplength=315).grid(row=6, column=0, sticky='w')
        label(self.right, 'Esperar antes de sair (segundos)', 7)
        combo(self.right, self.leave_delay, list(LEAVE_DELAYS), 8, self.controller.set_leave_delay)
        ctk.CTkButton(self.right, text='Conectar extensão · instruções', command=self.show_meet_help, height=34, corner_radius=10,
            fg_color=c['surface'], hover_color=c['line'], text_color=c['text'], font=font).grid(row=9, column=0, sticky='ew', pady=(14, 8))
        ctk.CTkButton(self.right, text='Abrir pasta da extensão', command=self.open_extension, height=34, corner_radius=10,
            fg_color=c['surface'], hover_color=c['line'], text_color=c['text'], font=font).grid(row=10, column=0, sticky='ew')
        self.sounds_on = tk.BooleanVar(value=state.sounds)
        self.call_sounds_on = tk.BooleanVar(value=state.call_sounds)
        sounds_row = ctk.CTkFrame(self.right, fg_color='transparent')
        sounds_row.grid(row=11, column=0, sticky='w', pady=(12, 0))
        ctk.CTkSwitch(sounds_row, text='Sons dos efeitos', variable=self.sounds_on,
            command=lambda: self.controller.set_sounds(self.sounds_on.get()), progress_color=c['accent'], text_color=c['text'], font=font).pack(anchor='w')
        ctk.CTkSwitch(sounds_row, text='Tocar os sons na chamada (Meet)', variable=self.call_sounds_on,
            command=lambda: self.controller.set_call_sounds(self.call_sounds_on.get()), progress_color=c['accent'], text_color=c['text'], font=font).pack(anchor='w', pady=(6, 0))
        self.meet_status = tk.StringVar(value=state.meet_status)
        self.meet_label = ctk.CTkLabel(self.right, textvariable=self.meet_status, wraplength=315, text_color=c['muted'], font=(FONT, 12), justify='left')
        self.meet_label.grid(row=12, column=0, sticky='ew', pady=(12, 0))
        self.inputs = [self.camera_combo, resolution_combo, backend_combo, hold_combo]
        root.bind('<F8>', lambda _event: self.controller.command('restore'))
        root.bind('<Escape>', lambda _event: self.hide_settings())
        root.protocol('WM_DELETE_WINDOW', self.close)
        if is_macos():
            # ⌘Q and the app menu must release the camera and the output like the close button.
            root.createcommand('tk::mac::Quit', self.close)
        self.controller.refresh_devices()
        self.poll()

    def apply(self, setter: Callable[[str], None], value: str) -> None:
        try:
            setter(value)
        except ValueError as error:
            self.status.set(str(error))

    def hide_settings(self) -> None:
        self.settings_visible = False
        self.settings_window.place_forget()

    def toggle_settings(self) -> None:
        if self.settings_visible:
            self.hide_settings()
            return
        self.settings_visible = True
        self.settings_window.configure(height=max(400, min(570, self.root.winfo_height() - 96)))
        self.settings_window.place(relx=1, x=-25, y=76, anchor='ne')
        self.settings_window.lift()
        self.settings_window.focus_set()

    def update_gesture_guide(self, state: ViewState) -> None:
        set_text(self.guide_title, state.guide_title)
        set_text(self.guide_instruction, state.guide_instruction)
        if self.guide_key == state.guide_image:
            return
        self.guide_key = state.guide_image
        self.guide_icon.grid_remove()
        self.guide_image = None
        path = resource_root() / 'assets' / 'gestures' / state.guide_image
        if path.is_file():
            try:
                with Image.open(path) as source:
                    if max(source.size) > 2048: raise ValueError('Ilustração grande demais.')
                    image = source.convert('RGBA')
                    image.thumbnail((512, 512))
                self.guide_image = ctk.CTkImage(light_image=image, dark_image=image, size=illustration_size(image.size, 64))
                self.guide_icon.configure(image=self.guide_image)
                self.guide_icon.grid(row=0, column=0, rowspan=2, padx=(0, 12))
            except (OSError, ValueError, Image.DecompressionBombError):
                self.guide_image = None
        if self.help_window is not None and self.help_window.winfo_exists(): self.help_window.destroy()

    def show_gesture_help(self) -> None:
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.lift()
            return
        state = self.controller.tick()
        window = ctk.CTkToplevel(self.root)
        self.help_window = window
        window.title(state.guide_title + ' · Sumi')
        set_window_icon(window)
        window.geometry('520x550')
        window.minsize(480, 460)
        window.transient(self.root)
        window.configure(fg_color=COLORS['shell'])
        window.bind('<F8>', lambda _event: self.controller.command('restore'))
        window.bind('<Escape>', lambda _event: window.destroy())
        content = ctk.CTkScrollableFrame(window, fg_color='transparent')
        content.pack(fill='both', expand=True, padx=22, pady=18)
        ctk.CTkLabel(content, text=state.guide_title, font=(FONT, 21, 'bold'), text_color=COLORS['text']).pack(anchor='w', pady=(0, 16))
        if self.guide_image is not None:
            source = self.guide_image.cget('light_image')
            large = ctk.CTkImage(light_image=source, dark_image=source, size=illustration_size(source.size, 280))
            ctk.CTkLabel(content, text='', image=large).pack(pady=(0, 14))
        for index, step in enumerate(state.guide_steps, 1):
            ctk.CTkLabel(content, text=f'{index}. {step}', font=(FONT, 14), text_color=COLORS['text'], wraplength=410, justify='left', anchor='w').pack(fill='x', pady=(0, 12))
        ctk.CTkLabel(content, text='A ativação alterna sair e voltar. O botão continua disponível; Restaurar ou F8 interrompe o efeito.', font=(FONT, 12), text_color=COLORS['muted'], wraplength=410, justify='left').pack(anchor='w', pady=(4, 12))

    def show_meet_help(self) -> None:
        help_window = ctk.CTkToplevel(self.root)
        help_window.title('Conectar a extensão')
        set_window_icon(help_window)
        help_window.geometry('580x430')
        help_window.transient(self.root)
        text = ('A extensão toca os sons dos efeitos na chamada e permite sair automaticamente.\n\n'
                '1. No Chrome/Edge, abra Extensões, ative Modo do desenvolvedor e carregue a pasta da extensão sem compactação.\n\n'
                '2. Pronto: com o Sumi aberto, a reunião do Meet é vinculada sozinha. Não há código para copiar.\n\n'
                '3. Opcional: ative Sair do Meet após desaparecer. F8 cancela durante a contagem.')
        ctk.CTkLabel(help_window, text=text, wraplength=510, justify='left', font=(FONT, 14), text_color=COLORS['text']).pack(padx=26, pady=26, anchor='w')
        ctk.CTkButton(help_window, text='Abrir guia completo', command=lambda: self.open(resource_root() / 'GUIA_RAPIDO.html'),
            fg_color=COLORS['accent'], hover_color=COLORS['accent_hover'], corner_radius=12).pack(padx=26, anchor='w')

    def open(self, path) -> None:
        try:
            open_path(path)
        except OSError:
            self.status.set('Não consegui abrir o arquivo.')

    def open_extension(self) -> None:
        folder = self.controller.extension_path()
        if folder is None:
            return
        try:
            open_path(folder)
        except OSError:
            self.controller.leave_note = 'Não consegui abrir a pasta da extensão.'

    def render(self, state: ViewState) -> None:
        set_text(self.state_text, state.phase_label)
        set_text(self.status, state.status)
        set_text(self.performance, state.performance)
        set_text(self.hint, state.hint)
        set_text(self.step_text, state.step)
        set_text(self.camera, state.camera)
        set_text(self.effect, state.effect)
        set_text(self.resolution, state.resolution)
        set_text(self.hold, state.hold)
        set_text(self.backend, state.output)
        set_text(self.leave_enabled, state.leave_enabled)
        set_text(self.leave_delay, state.leave_delay)
        set_text(self.background_mode, 'Em movimento' if state.dynamic_background else 'Estático')
        set_text(self.background_description, state.background_description)
        set_text(self.output_help, state.output_help)
        set_text(self.meet_status, state.meet_status)
        set_text(self.main_meet_notice, state.main_notice)
        self.update_gesture_guide(state)
        if self.last_progress != state.progress:
            self.last_progress = state.progress
            self.progress.set(state.progress)
        controls = (state.primary_label, state.primary_enabled, state.recalibrate_enabled, state.start_label,
                    state.start_enabled, state.inputs_enabled, state.refresh_enabled, tuple(state.cameras),
                    state.meet_available)
        if self.controls_state != controls:
            self.controls_state = controls
            on = lambda flag: 'normal' if flag else 'disabled'
            self.primary.configure(text=state.primary_label, state=on(state.primary_enabled))
            self.recalibrate.configure(state=on(state.recalibrate_enabled))
            self.start_button.configure(text=state.start_label, state=on(state.start_enabled))
            self.refresh_button.configure(state=on(state.refresh_enabled))
            for entry in self.inputs: entry.configure(state='readonly' if state.inputs_enabled else 'disabled')
            self.camera_combo.configure(values=state.cameras,
                                        state='readonly' if state.inputs_enabled and state.cameras else 'disabled')
            self.leave_toggle.configure(state=on(state.meet_available))
        if state.frame is not None and self.preview_revision != state.preview_revision:
            self.preview_revision = state.preview_revision
            frame = state.frame
            height, width = frame.shape[:2]
            scale = min(max(100, self.preview.winfo_width() - 4) / width, max(100, self.preview.winfo_height() - 4) / height)
            small = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_AREA)
            image = Image.fromarray(cv2.cvtColor(cv2.flip(small, 1), cv2.COLOR_BGR2RGB))
            self.image = ImageTk.PhotoImage(image)
            self.preview.configure(image=self.image, text='')

    def poll(self) -> None:
        if self.closing: return
        if self.hotkey.requested.is_set():
            self.hotkey.requested.clear()
            self.controller.command('restore')
        if self.hotkey.ready.is_set():
            set_text(self.shortcut, 'Tudo local · F8 restaura mesmo fora desta janela' if self.hotkey.registered else 'F8 só nesta janela · atalho global indisponível')
        self.render(self.controller.tick())
        available = max(270, self.center.winfo_width() - 32)
        if self.wrap_width != available:
            self.wrap_width = available
            self.hint_label.configure(wraplength=available)
            self.step_label.configure(wraplength=available)
            self.guide_label.configure(wraplength=max(350, available - 190))
        self.root.after(33, self.poll)

    def close(self) -> None:
        if self.closing: return
        self.closing = True
        self.controller.close()
        self.hotkey.close()
        self._finish_close()

    def _finish_close(self) -> None:
        if not self.controller.stopped(): self.root.after(100, self._finish_close)
        else: self.root.destroy()


def main() -> None:
    set_process_identity()
    root = ctk.CTk()
    App(root)
    root.mainloop()
