from speechweave.version import __version__
from speechweave.async_client import AsyncSpeechWeaveClient
from speechweave.client import SpeechWeaveClient
from speechweave.errors import SpeechWeaveError
from speechweave.mime import infer_content_type
from speechweave.namespaces.assembly_compat import AssemblyTranscripts, AsyncAssemblyTranscripts
from speechweave.namespaces.deepgram_compat import AsyncDeepgramListen, DeepgramListen
from speechweave.namespaces.jobs import AsyncJobs, Jobs
from speechweave.namespaces.openai_compat import AsyncOpenAiAudio, OpenAiAudio
from speechweave.polling import async_wait_for_job, wait_for_job
from speechweave.webhooks import verify_webhook


class SpeechWeave(SpeechWeaveClient):
	def __init__(
		self,
		*args,
		**kwargs,
	):

		super().__init__(
			*args,
			**kwargs,
		)
		self.audio = OpenAiAudio(self)
		self.listen = DeepgramListen(self)
		self.transcripts = AssemblyTranscripts(self)
		self.jobs = Jobs(self)


class AsyncSpeechWeave(AsyncSpeechWeaveClient):
	def __init__(
		self,
		*args,
		**kwargs,
	):

		super().__init__(
			*args,
			**kwargs,
		)
		self.audio = AsyncOpenAiAudio(self)
		self.listen = AsyncDeepgramListen(self)
		self.transcripts = AsyncAssemblyTranscripts(self)
		self.jobs = AsyncJobs(self)


__all__ = [
	"AsyncAssemblyTranscripts",
	"AsyncDeepgramListen",
	"AsyncJobs",
	"AsyncOpenAiAudio",
	"AsyncSpeechWeave",
	"AsyncSpeechWeaveClient",
	"AssemblyTranscripts",
	"DeepgramListen",
	"Jobs",
	"OpenAiAudio",
	"SpeechWeave",
	"SpeechWeaveClient",
	"SpeechWeaveError",
	"__version__",
	"async_wait_for_job",
	"infer_content_type",
	"verify_webhook",
	"wait_for_job",
]
