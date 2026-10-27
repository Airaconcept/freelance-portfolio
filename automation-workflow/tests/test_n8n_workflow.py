"""Static checks for n8n/daily-digest-workflow.json, plus a smoke run of every Code node
in Node.js with a minimal mock of n8n's $input / $() / $getWorkflowStaticData (skipped if node is missing).
Run with:  python -m unittest
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / "n8n" / "daily-digest-workflow.json"

HARNESS = r"""
const code = %s;
const input = %s;
const feedList = %s;
const store = {};
const $input = { all: () => input.map(j => ({ json: j })), first: () => ({ json: input[0] || {} }) };
const $ = (name) => ({ itemMatching: (i) => ({ json: feedList[Math.min(i, feedList.length - 1)] }), all: () => feedList.map(j => ({ json: j })) });
const $getWorkflowStaticData = () => store;
const run = new Function('$input', '$', '$getWorkflowStaticData', code);
const first = run($input, $, $getWorkflowStaticData);
const second = run($input, $, $getWorkflowStaticData);
console.log(JSON.stringify({ first, second }));
"""


def run_code(js, input_items, feed_list=()):
    src = HARNESS % (json.dumps(js), json.dumps(input_items), json.dumps(list(feed_list) or [{}]))
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


class WorkflowStructureTest(unittest.TestCase):
    def setUp(self):
        self.wf = json.loads(WF.read_text())
        self.nodes = {n["name"]: n for n in self.wf["nodes"]}

    def test_required_keys(self):
        for key in ("name", "nodes", "connections", "settings"):
            self.assertIn(key, self.wf)
        for n in self.wf["nodes"]:
            for key in ("id", "name", "type", "typeVersion", "position", "parameters"):
                self.assertIn(key, n, n.get("name"))
            self.assertTrue(n["type"].startswith("n8n-nodes-base."))
        self.assertEqual(len(self.nodes), len(self.wf["nodes"]), "node names must be unique")
        self.assertEqual(len({n["id"] for n in self.wf["nodes"]}), len(self.wf["nodes"]), "ids must be unique")

    def test_connections_point_to_real_nodes(self):
        for src, conn in self.wf["connections"].items():
            self.assertIn(src, self.nodes)
            for branch in conn["main"]:
                for c in branch:
                    self.assertIn(c["node"], self.nodes)
                    self.assertEqual(c["type"], "main")
        merge_inputs = sorted(c["index"] for conn in self.wf["connections"].values()
                              for b in conn["main"] for c in b if c["node"] == "Merge Sources")
        self.assertEqual(merge_inputs, [0, 1])

    def test_every_node_reachable_from_trigger(self):
        seen, todo = set(), ["Every Day 08:00"]
        while todo:
            n = todo.pop()
            seen.add(n)
            for b in self.wf["connections"].get(n, {}).get("main", []):
                todo += [c["node"] for c in b if c["node"] not in seen]
        self.assertEqual(seen, set(self.nodes))


@unittest.skipUnless(shutil.which("node"), "Node.js not installed")
class CodeNodeSmokeTest(unittest.TestCase):
    def setUp(self):
        self.nodes = {n["name"]: n for n in json.loads(WF.read_text())["nodes"]}

    def js(self, name):
        return self.nodes[name]["parameters"]["jsCode"]

    def test_feed_list(self):
        out = run_code(self.js("Feed List"), [])["first"]
        self.assertTrue(all("url" in i["json"] for i in out))

    def test_pipeline(self):
        feeds = [{"source": "Feed A", "url": "http://a"}]
        rss = [{"title": " Hello   world ", "link": "http://a/1", "guid": "1"}, {"error": "boom"}]
        feed_items = [i["json"] for i in run_code(self.js("Normalize Feed Items"), rss, feeds)["first"]]
        self.assertEqual(feed_items[0]["title"], "Hello world")
        page_items = [i["json"] for i in run_code(self.js("Normalize Page Items"), [{"quotes": ["q1", " "]}])["first"]]
        self.assertEqual(len(page_items), 1)

        res = run_code(self.js("New Items + Markdown Digest"), feed_items + page_items + [{}])
        first, second = res["first"][0]["json"], res["second"][0]["json"]
        self.assertEqual(first["count"], 2)                     # error + empty items dropped
        self.assertIn("[Hello world](http://a/1)", first["markdown"])
        self.assertEqual(second["count"], 0)                    # static data remembers what was sent


if __name__ == "__main__":
    unittest.main()
