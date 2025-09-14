from bs4 import BeautifulSoup


def split_quill(html: str) -> list[str]:
	"""Split a Text Editor HTML string into a list of HTML strings, each representing a direct child of the editor div.

	This is useful for breaking text-editor content into separate rows in a print format."""
	soup = BeautifulSoup(html, "html.parser")
	nested_divs = soup.find_all("div", recursive=False)

	if len(nested_divs) != 1:
		# If the content is not wrapped in a single div, return the original HTML
		return [html]

	div = nested_divs[0]
	if div.has_attr("class") and "ql-editor" in div["class"]:
		return [f'<div class="ql-editor">{str(child)}</div>' for child in div.children]
	else:
		return [str(child) for child in div.children]
