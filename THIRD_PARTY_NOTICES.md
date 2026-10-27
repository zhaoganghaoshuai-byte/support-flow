# Third-party references

SupportFlow independently implements the support and ticketing domain while referring to DeerFlow's public architecture and extension contract. In particular, the optional adapter follows the public plugin pattern demonstrated in DeerFlow's bookmark extension. DeerFlow is licensed under MIT; its notice is retained below. No DeerFlow frontend assets or branding are copied.

Reference: https://github.com/bytedance/deer-flow

```text
MIT License

Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
Copyright (c) 2025-2026 DeerFlow Authors
Copyright (c) 2023 shadcn (UI component reference)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Runtime and UI libraries retain their respective licenses in their distributions, including FastAPI, SQLAlchemy, LangChain, LangGraph, React, Vite and Lucide.

The UI also uses Tailwind CSS, Radix primitives and shadcn-style components. The shadcn/ui component reference is MIT licensed: https://github.com/shadcn-ui/ui/blob/main/LICENSE.md. Its copyright notice is included in the shared MIT text above. Library license files remain in the installed distributions.

Knowledge summaries are original concise Chinese summaries linked to official sources. Source URLs, upstream license links, retrieval times and hashes are recorded in `backend/supportflow/corpus/official/manifest.json` and explained in `docs/knowledge-sources.md`. Full extracted source caches are not committed to the repository.
