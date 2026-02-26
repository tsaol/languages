"""HTTP client for EngLearn web API. Used by the CLI as a thin frontend."""
import os
import json
import requests

DEFAULT_SERVER = os.environ.get("ENGLEARN_SERVER", "")
CONFIG_PATH = os.path.expanduser("~/.englearn_cli.json")


def _load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _save_config(cfg):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f)


class Client:
    def __init__(self, server=None):
        cfg = _load_config()
        self.server = server or cfg.get("server", DEFAULT_SERVER)
        self.session = requests.Session()
        # Restore cookies
        cookies = cfg.get("cookies", {})
        for k, v in cookies.items():
            self.session.cookies.set(k, v)

    def _url(self, path):
        return self.server.rstrip("/") + path

    def _save_cookies(self):
        cfg = _load_config()
        cfg["server"] = self.server
        cfg["cookies"] = dict(self.session.cookies)
        _save_config(cfg)

    def login(self, username, password):
        resp = self.session.post(self._url("/login"), data={
            "username": username, "password": password,
        }, allow_redirects=False)
        if resp.status_code in (302, 200):
            self._save_cookies()
            return True
        return False

    def get_review_cards(self, deck=None, limit=20):
        params = {"limit": limit}
        if deck:
            params["deck"] = deck
        resp = self.session.get(self._url("/api/review/cards"), params=params)
        if resp.status_code == 401:
            return None
        return resp.json()

    def submit_review(self, card_id, rating):
        resp = self.session.post(self._url("/review/answer"),
                                 json={"card_id": card_id, "rating": rating})
        return resp.json()

    def get_talk_scenarios(self, limit=10, include_all=False):
        params = {"limit": limit}
        if include_all:
            params["all"] = "1"
        resp = self.session.get(self._url("/api/talk/scenarios"), params=params)
        if resp.status_code == 401:
            return None
        return resp.json()

    def submit_talk(self, answer, context, pattern, ai_says, good_responses, scenario_id=None):
        resp = self.session.post(self._url("/talk/answer"), json={
            "answer": answer,
            "context": context,
            "pattern": pattern,
            "ai_says": ai_says,
            "good_responses": good_responses,
            "scenario_id": scenario_id,
        })
        return resp.json()

    def get_stats(self):
        resp = self.session.get(self._url("/api/stats"))
        if resp.status_code == 401:
            return None
        return resp.json()

    def translate_word(self, word):
        resp = self.session.post(self._url("/vocab/translate"), json={"word": word})
        return resp.json()

    def save_vocab(self, word, chinese, category="talk"):
        resp = self.session.post(self._url("/vocab/add"), json={
            "word": word, "chinese": chinese, "category": category,
        })
        return resp.json()

    def get_chat_roles(self):
        resp = self.session.get(self._url("/api/chat/roles"))
        if resp.status_code == 401:
            return None
        return resp.json()

    def start_chat_session(self, role_id, scenario_id=None):
        resp = self.session.post(self._url("/api/chat/start"), json={
            "role_id": role_id, "scenario_id": scenario_id or "",
        })
        if resp.status_code == 401:
            return None
        return resp.json()

    def send_chat_message(self, role_id, message, scenario_id=None):
        resp = self.session.post(self._url("/api/chat/send"), json={
            "role_id": role_id, "message": message,
            "scenario_id": scenario_id or "",
        })
        if resp.status_code == 401:
            return None
        return resp.json()

    def get_chat_history(self, role_id, limit=20, scenario_id=None):
        params = {"role_id": role_id, "limit": limit}
        if scenario_id:
            params["scenario_id"] = scenario_id
        resp = self.session.get(self._url("/api/chat/history"), params=params)
        if resp.status_code == 401:
            return None
        return resp.json()
