using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace NekoTerrariaLink
{
    public class Dict
    {
        private readonly Dictionary<string, object> _m = new();

        public object this[string k]
        {
            get => _m.TryGetValue(k, out var v) ? v : null;
            set => _m[k] = value;
        }

        public string GetValue(string k) => this[k] as string ?? "";
        public double GetNum(string k) => Convert.ToDouble(this[k] ?? 0, CultureInfo.InvariantCulture);
        public List<string> GetArray(string k) => this[k] as List<string> ?? new List<string>();

        public string ToJson() => Serialize(this);

        private static string Serialize(object o)
        {
            switch (o)
            {
                case null: return "null";
                case string s: return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
                case double d: return d.ToString(CultureInfo.InvariantCulture);
                case int i: return i.ToString(CultureInfo.InvariantCulture);
                case bool b: return b ? "true" : "false";
                case Dict d:
                    var sb = new StringBuilder("{");
                    bool first = true;
                    foreach (var kv in d._m)
                    {
                        if (!first) sb.Append(",");
                        first = false;
                        sb.Append("\"").Append(kv.Key).Append("\":").Append(Serialize(kv.Value));
                    }
                    sb.Append("}");
                    return sb.ToString();
                case List<Dict> ld:
                    var s2 = new StringBuilder("[");
                    for (int i = 0; i < ld.Count; i++)
                    {
                        if (i > 0) s2.Append(",");
                        s2.Append(Serialize(ld[i]));
                    }
                    s2.Append("]");
                    return s2.ToString();
                case List<string> ls:
                    var s3 = new StringBuilder("[");
                    for (int i = 0; i < ls.Count; i++)
                    {
                        if (i > 0) s3.Append(",");
                        s3.Append(Serialize(ls[i]));
                    }
                    s3.Append("]");
                    return s3.ToString();
                default: return "null";
            }
        }
    }

    public static class JsonParser
    {
        public static Dict Parse(string json) => (Dict)ParseValue(json, ref json);

        private static object ParseValue(string src, ref string rest)
        {
            rest = rest.TrimStart();
            if (rest.Length == 0) return null;
            char c = rest[0];
            if (c == '{') return ParseObject(ref rest);
            if (c == '[') return ParseArray(ref rest);
            if (c == '"') return ParseString(ref rest);
            if (c == 't' || c == 'f') return ParseBool(ref rest);
            return ParseNumber(ref rest);
        }

        private static Dict ParseObject(ref string rest)
        {
            rest = rest.Substring(1).TrimStart();
            var d = new Dict();
            if (rest.StartsWith("}")) { rest = rest.Substring(1); return d; }
            while (true)
            {
                string key = ParseString(ref rest).ToString();
                rest = rest.TrimStart();
                rest = rest.Substring(1).TrimStart(); // skip :
                object val = ParseValue(rest, ref rest);
                d[key] = val;
                rest = rest.TrimStart();
                if (rest.StartsWith(",")) rest = rest.Substring(1);
                else if (rest.StartsWith("}")) { rest = rest.Substring(1); break; }
            }
            return d;
        }

        private static object ParseArray(ref string rest)
        {
            rest = rest.Substring(1).TrimStart();
            var list = new List<object>();
            while (!rest.StartsWith("]"))
            {
                var v = ParseValue(rest, ref rest);
                if (v != null) list.Add(v);
                rest = rest.TrimStart();
                if (rest.StartsWith(",")) rest = rest.Substring(1);
            }
            rest = rest.Substring(1);
            // 判断元素类型：纯字符串数组返回 List<string>，否则 List<Dict>
            bool allStr = true;
            foreach (var e in list)
                if (!(e is string)) { allStr = false; break; }
            if (allStr)
            {
                var sl = new List<string>();
                foreach (var e in list) sl.Add((string)e);
                return sl;
            }
            var dl = new List<Dict>();
            foreach (var e in list)
                if (e is Dict d) dl.Add(d);
            return dl;
        }

        private static StringBuilder ParseString(ref string rest)
        {
            rest = rest.Substring(1); // skip opening "
            var sb = new StringBuilder();
            while (rest.Length > 0 && rest[0] != '"')
            {
                if (rest[0] == '\\' && rest.Length > 1)
                {
                    sb.Append(rest[1]);
                    rest = rest.Substring(2);
                }
                else
                {
                    sb.Append(rest[0]);
                    rest = rest.Substring(1);
                }
            }
            if (rest.Length > 0) rest = rest.Substring(1);
            return sb;
        }

        private static bool ParseBool(ref string rest)
        {
            if (rest.StartsWith("true")) { rest = rest.Substring(4); return true; }
            rest = rest.Substring(5); return false;
        }

        private static double ParseNumber(ref string rest)
        {
            int i = 0;
            while (i < rest.Length && (char.IsDigit(rest[i]) || rest[i] == '.' || rest[i] == '-'))
                i++;
            var num = rest.Substring(0, i);
            rest = rest.Substring(i);
            return double.Parse(num, CultureInfo.InvariantCulture);
        }
    }
}
