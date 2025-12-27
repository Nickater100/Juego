# project/engines/world_engine/dialogue_system.py
import pygame
import json
import os
from core.assets import asset_path


class DialogueSystem:
    def __init__(self, world_state):
        self.ws = world_state

        self.active = False
        self.speaker = ""
        self.lines = []
        self.index = 0

        self.options = []
        self.option_index = 0
        self.context = {}

        self.ui_font = pygame.font.SysFont(None, 24)

        # Retrato del protagonista (diálogos) — igual que antes
        raw_portrait = pygame.image.load(
            asset_path("sprites", "protagonist", "portrait.png")
        ).convert_alpha()

        self.portrait_original = self._trim_transparent(raw_portrait)
        self.portrait_cover = None
        self.portrait_cover_key = None

    # -------------------------
    # API
    # -------------------------
    def open(self, speaker: str, lines, options=None, context=None):
        self.active = True
        self.speaker = speaker
        self.lines = list(lines) if lines else ["..."]
        self.index = 0
        self.options = list(options) if options else []
        self.option_index = 0
        self.context = dict(context) if context else {}

        self.ws.input_locked = True

    def close(self):
        after = self.context.get("after_dialogue")

        # Caso especial: si estamos en assign_roles y el usuario cierra con ESC
        # lo resuelve handle_event(), acá cerramos normal.
        self.active = False
        self.speaker = ""
        self.lines = []
        self.index = 0
        self.options = []
        self.option_index = 0
        self.context = {}

        self.ws.input_locked = False

        if after:
            after()

    # -------------------------
    # Input
    # -------------------------
    def handle_event(self, event) -> bool:
        if not self.active:
            return False

        if event.type != pygame.KEYDOWN:
            return True

        # ESC/BACKSPACE: cerrar
        if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            # Igual que antes: evitar cuelgue durante assign_roles
            if self.context.get("event") == "assign_roles" and getattr(self.ws, "_assign_active", False):
                self.ws._assign_idx += 1
                self.ws._show_assign_prompt()
                return True

            self.close()
            return True

        # Con opciones
        if self.options:
            if event.key == pygame.K_w:
                self.option_index = (self.option_index - 1) % len(self.options)
                return True

            if event.key == pygame.K_s:
                self.option_index = (self.option_index + 1) % len(self.options)
                return True

            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._confirm_option()
                return True

            return True

        # Sin opciones: avanzar líneas
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.index + 1 < len(self.lines):
                self.index += 1
            else:
                self.close()
            return True

        return True

    # -------------------------
    # Opciones / acciones
    # -------------------------
    def _confirm_option(self):
        if not self.options:
            self.close()
            return

        opt = self.options[self.option_index]
        action = opt.get("action", "close")

        # Eventos (runner)
        if action == "event_continue":
            self.close()
            self.ws.event_runner.advance()
            return

        # assign_roles
        if isinstance(action, str) and action.startswith("assign_role:"):
            role = action.split(":", 1)[1]
            self.ws.assign_role(role)
            return

        # close
        if action == "close":
            self.close()
            return

        # recruit
        if action == "recruit":
            unit_id = opt.get("unit_id", "unknown")
            self.ws._dialogue_action_recruit(unit_id, speaker=self.speaker, npc_id=self.context.get("npc_id"))
            return

        # Acción desconocida
        self.close()

    # -------------------------
    # Render (COPIADO del ZIP, mismo layout/escala)
    # -------------------------
    def render(self, screen):
        if not self.active:
            return

        w, h = screen.get_width(), screen.get_height()

        box_h = 140
        margin = 16
        padding = 12
        gap = 16

        box_rect = pygame.Rect(margin, h - box_h - margin, w - margin * 2, box_h)
        pygame.draw.rect(screen, (0, 0, 0), box_rect)
        pygame.draw.rect(screen, (255, 255, 255), box_rect, 2)

        content_w = box_rect.width - padding * 2
        content_h = box_rect.height - padding * 2

        portrait_area_w = int(content_w * 0.25)
        text_area_w = content_w - portrait_area_w - gap

        portrait_area = pygame.Rect(
            box_rect.x + padding,
            box_rect.y + padding,
            portrait_area_w,
            content_h
        )

        text_area = pygame.Rect(
            portrait_area.right + gap,
            box_rect.y + padding,
            text_area_w,
            content_h
        )

        # --- Retrato dinámico según speaker (IGUAL que antes) ---
        portrait_surface = self.portrait_original
        portrait_key = "protagonist"
        speaker_key = self.speaker.strip().lower().replace(" ", "_")

        if speaker_key in ["marian_vell", "selma_ironrose", "loren_valcrest", "iraen_falk", "elinya_brightwell"]:
            try:
                npc_json_path = asset_path("sprites", "npcs", speaker_key, f"{speaker_key}.json")
                if os.path.exists(npc_json_path):
                    with open(npc_json_path, "r", encoding="utf-8") as f:
                        npc_data = json.load(f)
                    portrait_path = npc_data.get("visual", {}).get("portrait")
                    if portrait_path:
                        surf = pygame.image.load(asset_path(*portrait_path.split("/"))).convert_alpha()
                        portrait_surface = self._trim_transparent(surf)
                        portrait_key = speaker_key
            except Exception:
                pass

        cache_key = (portrait_area.w, portrait_area.h, portrait_key)
        if getattr(self, "portrait_cover_key", None) != cache_key:
            ow, oh = portrait_surface.get_width(), portrait_surface.get_height()
            scale_needed = min(portrait_area.w / ow, portrait_area.h / oh)
            new_w = int(ow * scale_needed)
            new_h = int(oh * scale_needed)
            scaled = pygame.transform.smoothscale(portrait_surface, (new_w, new_h))
            panel = pygame.Surface((portrait_area.w, portrait_area.h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 255))
            px = (portrait_area.w - new_w) // 2
            py = (portrait_area.h - new_h) // 2
            panel.blit(scaled, (px, py))
            self.portrait_cover = panel
            self.portrait_cover_key = cache_key

        screen.blit(self.portrait_cover, (portrait_area.x, portrait_area.y))

        def wrap_lines(text: str, font: pygame.font.Font, max_w: int):
            words = text.split(" ")
            lines = []
            current = ""
            for word in words:
                test = word if not current else current + " " + word
                if font.size(test)[0] <= max_w:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            return lines

        text_x = text_area.x
        text_y = text_area.y

        if self.speaker:
            name_surf = self.ui_font.render(self.speaker + ":", True, (255, 255, 255))
            screen.blit(name_surf, (text_x, text_y))
            text_y += 22

        current_text = self.lines[self.index] if self.lines else "..."
        wrapped = wrap_lines(current_text, self.ui_font, text_area.width)

        line_h = 22
        options_lines = len(self.options) if self.options else 0
        options_space = options_lines * line_h + (10 if options_lines else 0)

        max_text_lines = max(1, (text_area.height - options_space - 24) // line_h)
        for i, line in enumerate(wrapped[:max_text_lines]):
            line_surf = self.ui_font.render(line, True, (255, 255, 255))
            screen.blit(line_surf, (text_x, text_y + i * line_h))

        if self.options:
            opt_y = text_y + min(len(wrapped), max_text_lines) * line_h + 10
            for i, opt in enumerate(self.options):
                prefix = "▶ " if i == self.option_index else "  "
                opt_surf = self.ui_font.render(prefix + opt.get("text", ""), True, (255, 255, 255))
                screen.blit(opt_surf, (text_area.x, opt_y + i * line_h))
            hint_text = "W/S: elegir  ENTER: confirmar  ESC: cerrar"
        else:
            hint_text = "ENTER/SPACE/ESC: cerrar"

        hint = self.ui_font.render(hint_text, True, (180, 180, 180))
        screen.blit(hint, (box_rect.x + box_rect.w - 380, box_rect.y + box_rect.h - 28))

    # -------------------------
    # Utils
    # -------------------------
    def _trim_transparent(self, surface: pygame.Surface) -> pygame.Surface:
        rect = surface.get_bounding_rect()
        return surface.subsurface(rect).copy()
