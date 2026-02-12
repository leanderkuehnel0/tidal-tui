from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Button, Static, Label, ProgressBar
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.message import Message
from textual.events import Event, MouseDown
import requests
import base64
import json
import mpv
from mpv import MPV # Explicitly import MPV class
from main import search_song, search_playlist, search_artist, play_song

class ResultClick(Message):
    """Custom message for when a result item is clicked or a menu action is chosen."""
    def __init__(self, item_id: str, item_type: str, action: str = "play", item_data: dict = None, index: int = -1) -> None:
        super().__init__()
        self.item_id = item_id
        self.item_type = item_type
        self.action = action
        self.item_data = item_data
        self.index = index

class ContextMenu(Static):
    """A minimal context menu."""
    def __init__(self, item_id: str, item_type: str, item_data: dict, options: list, index: int = -1, **kwargs):
        super().__init__(**kwargs)
        self.item_id = item_id
        self.item_type = item_type
        self.item_data = item_data
        self.options = options # List of (label, action_id)
        self.index = index

    def compose(self) -> ComposeResult:
        for label, action_id in self.options:
            yield Button(label, id=action_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = str(event.button.id)
        self.post_message(ResultClick(self.item_id, self.item_type, action, self.item_data, self.index))
        self.remove()

class ClickableStatic(Static):
    """A Static widget that can be clicked and right-clicked."""
    def __init__(self, renderable, item_id: str, item_type: str, item_data: dict, **kwargs):
        super().__init__(renderable, **kwargs)
        self.item_id = item_id
        self.item_type = item_type
        self.item_data = item_data

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 1: # Left click
            self.post_message(ResultClick(self.item_id, self.item_type, "play", self.item_data))
        elif event.button == 3: # Right click
            options = [("Play", "play"), ("Add to Queue", "queue"), ("Play Next", "play_next")]
            self.app.show_context_menu(self.item_id, self.item_type, self.item_data, options, event.screen_x, event.screen_y)
        event.stop()

class QueueItem(Static):
    """A Static widget for items in the queue."""
    def __init__(self, renderable, item_data: dict, index: int, **kwargs):
        super().__init__(renderable, **kwargs)
        self.item_data = item_data
        self.index = index

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 3: # Right click
            options = [("Move Up", "move_up"), ("Move Down", "move_down"), ("Remove", "remove")]
            self.app.show_context_menu(self.item_data['id'], "song", self.item_data, options, event.screen_x, event.screen_y, self.index)
        event.stop()

class MusicPlayerTUI(App):
    """A Textual music player TUI."""

    CSS_PATH = "tui.css" # Link the CSS file

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
        ("s", "stop_playback", "Stop"),
        ("space", "toggle_pause", "Pause/Resume"),
        ("n", "next_song", "Next Song"),
        ("p", "prev_song", "Previous Song"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = MPV(ytdl=True, video=False, idle=True, input_default_bindings=True, input_vo_keyboard=True)
        self.is_paused = False
        self.is_playing = False
        self.search_type = "song" # Default search type
        self.song_results_data = []
        self.playlist_results_data = []
        self.artist_results_data = []
        self.queue = [] # List of song objects
        self.history = [] # For previous song support
        self.current_song_data = None

        # Observe properties for playback state
        self.player.observe_property('pause', self.mpv_property_change)
        self.player.observe_property('idle-active', self.mpv_property_change)
        self.player.observe_property('time-pos', self.mpv_property_change)
        self.player.observe_property('duration', self.mpv_property_change)

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        pass

    def mpv_property_change(self, name, value):
        """Callback for observed mpv properties (runs in a separate thread)."""
        if name == 'pause':
            self.is_paused = value
        elif name == 'idle-active':
            if value and self.is_playing:
                self.call_from_thread(self.action_next_song)
            self.is_playing = not value
        elif name == 'time-pos':
            if value is not None:
                self.call_from_thread(self.update_progress, value)
        elif name == 'duration':
            if value is not None:
                self.call_from_thread(self.set_duration, value)
        
        try:
            self.call_from_thread(self.update_playback_status)
        except RuntimeError:
            pass # App might be shutting down
    
    def set_duration(self, value):
        try:
            self.query_one("#playback_progress", ProgressBar).total = value
        except: pass

    def update_progress(self, value):
        try:
            self.query_one("#playback_progress", ProgressBar).progress = value
        except: pass

    def update_playback_status(self):
        status_bar = self.query_one("#status_bar", Static)
        if self.is_playing:
            song_title = self.current_song_data['title'] if self.current_song_data else "Unknown"
            status_text = f"Playing: {song_title}"
            if self.is_paused:
                status_bar.update(f"Paused - {status_text}")
            else:
                status_bar.update(f"{status_text}")
        else:
            status_bar.update("Ready.")

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Container(id="app_grid"):
            with Container(id="search_bar_container"):
                yield Input(placeholder="Search songs...", id="search_input")
                yield Button("S", id="search_type_button")
            with Horizontal(id="main_content"):
                with VerticalScroll(id="results_container"):
                    pass # Results will be mounted here
                with Vertical(id="queue_panel"):
                    yield Label("Queue", id="queue_label")
                    with VerticalScroll(id="queue_list"):
                        pass
            with Container(id="player_footer"):
                with Horizontal(id="footer_controls"):
                    yield Button("⏮", id="prev_button", classes="footer_btn")
                    yield Button("⏯", id="pause_resume_footer_button", classes="footer_btn")
                    yield Button("⏭", id="next_button", classes="footer_btn")
                    yield ProgressBar(id="playback_progress", show_eta=False, show_percentage=False)
        yield Footer()
        yield Static("Ready.", id="status_bar")

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_quit(self) -> None:
        """An action to quit the application."""
        if self.player:
            self.player.terminate()
        self.exit()

    def action_stop_playback(self) -> None:
        """Binding action for Stop."""
        if self.player:
            self.player.stop()
            self.query_one("#status_bar", Static).update("Playback stopped.")

    def action_toggle_pause(self) -> None:
        """Binding action for Pause/Resume."""
        if self.player and self.is_playing:
            self.player.pause = not self.is_paused
        else:
            self.query_one("#status_bar", Static).update("Nothing playing.")

    def action_next_song(self) -> None:
        """Play the next song in the queue."""
        if self.current_song_data:
            self.history.append(self.current_song_data)
        if self.queue:
            next_song = self.queue.pop(0)
            self.play_selected_item(next_song['id'], "song", next_song)
            self.update_queue_display()
        else:
            self.current_song_data = None
            self.action_stop_playback()

    def action_prev_song(self) -> None:
        """Play the previous song."""
        if self.history:
            if self.current_song_data:
                self.queue.insert(0, self.current_song_data)
            prev_song = self.history.pop()
            self.play_selected_item(prev_song['id'], "song", prev_song)
            self.update_queue_display()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search_input":
            self.search(self.search_type)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search_type_button":
            self.cycle_search_type()
        elif event.button.id == "prev_button":
            self.action_prev_song()
        elif event.button.id == "pause_resume_footer_button":
            self.action_toggle_pause()
        elif event.button.id == "next_button":
            self.action_next_song()

    def cycle_search_type(self) -> None:
        types = ["song", "playlist", "artist"]
        current_index = types.index(self.search_type)
        self.search_type = types[(current_index + 1) % len(types)]
        
        button = self.query_one("#search_type_button", Button)
        input_widget = self.query_one("#search_input", Input)
        
        button.label = self.search_type[0].upper()
        input_widget.placeholder = f"Search {self.search_type}s..."
        
        query = input_widget.value
        if query:
            self.search(self.search_type)

    def search(self, search_type: str) -> None:
        query = self.query_one("#search_input", Input).value
        if not query:
            return

        # Clear previous results
        results_container = self.query_one("#results_container")
        results_container.remove_children()

        if search_type == "song":
            self.search_songs(query)
        elif search_type == "playlist":
            self.search_playlists(query)
        elif search_type == "artist":
            self.search_artists(query)

    def _get_artist_name(self, artist_data) -> str:
        """Helper to extract artist name from potentially complex artist data."""
        if isinstance(artist_data, dict):
            return artist_data.get('name', 'Unknown Artist')
        return str(artist_data)

    def search_songs(self, query: str) -> None:
        try:
            songs = search_song(query) # Using the imported function
            self.song_results_data = songs # Store full song objects
            results_container = self.query_one("#results_container")
            if songs:
                for i, song in enumerate(songs):
                    artist_name = self._get_artist_name(song.get('artist', 'Unknown'))
                    # Using Rich markup for better looking list items
                    label = f"[bold]{i+1}. {song['title']}[/bold] - [italic]{artist_name}[/italic]"
                    results_container.mount(ClickableStatic(label, item_id=song['id'], item_type="song", item_data=song))
        except: pass

    def search_playlists(self, query: str) -> None:
        try:
            playlists = search_playlist(query) # Using the imported function
            self.playlist_results_data = playlists # Store full playlist objects
            results_container = self.query_one("#results_container")
            if playlists:
                for i, pl in enumerate(playlists):
                    artist_name = self._get_artist_name(pl.get('artist', 'Unknown'))
                    # Using Rich markup for better looking list items
                    label = f"[bold]{i+1}. {pl.get('title', 'Unknown Title')}[/bold] - [italic]{artist_name}[/italic]"
                    results_container.mount(ClickableStatic(label, item_id=pl['id'], item_type="playlist", item_data=pl))
        except: pass

    def search_artists(self, query: str) -> None:
        try:
            artists = search_artist(query) # Using the imported function
            self.artist_results_data = artists # Store full artist objects
            results_container = self.query_one("#results_container")
            if artists:
                for i, artist in enumerate(artists):
                    # Using Rich markup for better looking list items
                    label = f"[bold]{i+1}. {artist.get('name', 'Unknown Artist')}[/bold]"
                    results_container.mount(ClickableStatic(label, item_id=artist['id'], item_type="artist", item_data=artist))
        except: pass

    def show_context_menu(self, item_id: str, item_type: str, item_data: dict, options: list, x: int, y: int, index: int = -1):
        """Show context menu at coordinates."""
        # Remove existing if any
        for node in self.query("ContextMenu"):
            node.remove()
        
        menu = ContextMenu(item_id, item_type, item_data, options, index)
        self.mount(menu)
        menu.styles.offset = (x, y)
        menu.focus()

    def on_result_click(self, message: ResultClick) -> None:
        """Called when a clickable result is clicked or context menu action."""
        if message.action == "play":
            self.play_selected_item(message.item_id, message.item_type, message.item_data)
        elif message.action == "queue":
            if message.item_type == "song":
                self.queue.append(message.item_data)
                self.update_queue_display()
        elif message.action == "play_next":
            if message.item_type == "song":
                self.queue.insert(0, message.item_data)
                self.update_queue_display()
        elif message.action == "remove":
            if 0 <= message.index < len(self.queue):
                self.queue.pop(message.index)
                self.update_queue_display()
        elif message.action == "move_up":
            if 0 < message.index < len(self.queue):
                self.queue[message.index], self.queue[message.index-1] = self.queue[message.index-1], self.queue[message.index]
                self.update_queue_display()
        elif message.action == "move_down":
            if 0 <= message.index < len(self.queue) - 1:
                self.queue[message.index], self.queue[message.index+1] = self.queue[message.index+1], self.queue[message.index]
                self.update_queue_display()

    def update_queue_display(self):
        """Update the queue list view."""
        queue_list = self.query_one("#queue_list", VerticalScroll)
        queue_list.remove_children()
        for i, song in enumerate(self.queue):
            artist_name = self._get_artist_name(song.get('artist', 'Unknown'))
            queue_list.mount(QueueItem(f"{i+1}. {song['title']} - {artist_name}", item_data=song, index=i, classes="queue_item"))

    def play_selected_item(self, item_id: str, item_type: str, item_data: dict = None) -> None:
        try:
            if item_type == "song":
                self.current_song_data = item_data
                play_song(item_id, self.player) # Using the imported function
        except Exception as e:
            self.query_one("#status_bar", Static).update(f"Error: {e}")


if __name__ == "__main__":
    app = MusicPlayerTUI()
    app.run()

