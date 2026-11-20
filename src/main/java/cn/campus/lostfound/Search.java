package cn.campus.lostfound;

import static cn.campus.lostfound.Support.*;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.*;
import java.text.Normalizer;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.regex.*;
import org.springframework.stereotype.Service;

@Service
public class Search {
    private final Db db;
    private final ObjectMapper json = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(2)).build();
    private final String endpoint = System.getProperty("app.ai","http://127.0.0.1:8765");
    // These are retrieval cutoffs, not probabilities of ownership.
    public static final double MIN_SCORE = 30.0;
    private static final double SEMANTIC_RECALL = .45;
    private static final List<List<String>> BRANDS = List.of(
        List.of("苹果","apple","iphone","ipad","macbook","airpods"),List.of("华为","huawei","mate","pura"),
        List.of("小米","xiaomi","redmi"),List.of("三星","samsung"),List.of("荣耀","honor"),List.of("oppo"),List.of("vivo"));
    private static final List<List<String>> OBJECTS = List.of(
        List.of("校园卡","学生卡","饭卡","餐卡"),List.of("身份证"),List.of("银行卡"),
        List.of("手机","iphone"),List.of("耳机","耳塞","airpods"),List.of("平板","ipad"),
        List.of("电脑","笔记本电脑","macbook"),List.of("包","背包","书包"),List.of("钥匙"),
        List.of("水杯","杯子","保温杯","水壶"),List.of("伞"),List.of("课本","教材","书籍"),
        List.of("眼镜","近视镜"),List.of("围巾"),List.of("外套","衣服"),List.of("u盘","优盘"));
    private static final Map<String,List<String>> TERMS = Map.of(
        "证件卡片",List.of("校园卡","学生卡","饭卡","身份证","银行卡"),"数码电子",List.of("手机","耳机","电脑","平板","充电器"),
        "钥匙",List.of("钥匙","门禁"),"包袋",List.of("书包","背包","电脑包","钱包"),"衣物配饰",List.of("外套","衣服","手表","围巾","帽子"),
        "水杯餐具",List.of("水杯","保温杯","杯子","饭盒"),"雨伞",List.of("雨伞","折叠伞","伞"),"书籍文具",List.of("书籍","课本","笔记本","文具"));
    private static final List<List<String>> CONFLICTS = List.of(List.of("黑色","白色","蓝色","红色","绿色","黄色","粉色","灰色","银色"));
    public Search(Db db) { this.db=db; }
    public static String normalize(String text) {
        return Normalizer.normalize(text,Normalizer.Form.NFKC).toLowerCase(Locale.ROOT).replace("学生卡","校园卡").replace("饭卡","校园卡").replace("校图书馆","图书馆").replace("图书馆大楼","图书馆").replaceAll("\\s+","");
    }
    private static Set<String> grams(String text) {
        Set<String> result = new LinkedHashSet<>(); Matcher matcher = Pattern.compile("[a-z0-9]+|[\\p{IsHan}]+").matcher(normalize(text));
        while(matcher.find()) { String token=matcher.group(); if(token.matches("[a-z0-9]+") || token.length()==1) result.add(token); else for(int index=0;index<token.length()-1;index++) result.add(token.substring(index,index+2)); }
        return result;
    }
    public static double lexical(String query,String document) {
        String normalized=normalize(document); Set<String> tokens=grams(query); if(tokens.isEmpty()) return 0;
        return tokens.stream().filter(normalized::contains).count()/(double)tokens.size();
    }
    public static int conflicts(String query,String document) {
        int count=0; String first=normalize(query),second=normalize(document);
        for(List<String> group:CONFLICTS) { List<String> wanted=group.stream().filter(first::contains).toList(); List<String> actual=group.stream().filter(second::contains).toList(); if(!wanted.isEmpty() && !actual.isEmpty() && Collections.disjoint(wanted,actual)) count++; }
        List<List<String>> wantedBrands=BRANDS.stream().filter(group->containsAny(first,group)).toList();
        List<List<String>> actualBrands=BRANDS.stream().filter(group->containsAny(second,group)).toList();
        if(!wantedBrands.isEmpty()&&!actualBrands.isEmpty()&&Collections.disjoint(wantedBrands,actualBrands))count++;
        Matcher models=Pattern.compile("(?:mate|iphone|nova|redmi|pura)\\s*\\d+[a-z]*").matcher(query.toLowerCase(Locale.ROOT));
        while(models.find()) { String model=normalize(models.group()); Matcher actual=Pattern.compile("(?:mate|iphone|nova|redmi|pura)\\d+[a-z]*").matcher(second); if(actual.find() && !model.equals(actual.group())) count++; }
        return count;
    }
    private static boolean containsAny(String text,List<String> terms) { return terms.stream().map(Search::normalize).anyMatch(text::contains); }
    private static boolean brandOnlyMatch(String query,String document) {
        String first=normalize(query),second=normalize(document);
        return BRANDS.stream().anyMatch(group->group.stream().map(Search::normalize).anyMatch(first::equals)&&containsAny(second,group));
    }
    public static boolean relevant(String query,String document,double semantic) {
        String first=normalize(query),second=normalize(document);
        if(conflicts(query,document)>0)return false;
        for(List<String> brand:BRANDS)if(containsAny(first,brand)&&!containsAny(second,brand))return false;
        // Object words and explicit product models are anchors: a shared color or location is insufficient.
        for(List<String> object:OBJECTS)if(containsAny(first,object)&&!containsAny(second,object))return false;
        Matcher models=Pattern.compile("(?:iphone|mate|nova|redmi|pura)\\d+[a-z]*").matcher(first);
        while(models.find())if(!Pattern.compile(Pattern.quote(models.group())+"(?![a-z0-9])").matcher(second).find())return false;
        return lexical(query,document)>0||brandOnlyMatch(query,document)||semantic>=SEMANTIC_RECALL;
    }
    public Map<String,Object> suggestions(String query) {
        Map<String,Object> values=new LinkedHashMap<>(); String normalized=normalize(query);
        TERMS.forEach((category,terms)-> { if(terms.stream().anyMatch(term->normalized.contains(normalize(term)))) values.putIfAbsent("category",category); });
        for(String location:List.of("图书馆","食堂","教学楼","操场","宿舍","体育馆")) if(normalized.contains(location)) { values.put("location",location); break; }
        LocalDate today=LocalDate.now(ZoneId.of("Asia/Shanghai"));
        if(query.contains("前天")) values.put("date",today.minusDays(2).toString()); else if(query.contains("昨天")) values.put("date",today.minusDays(1).toString()); else if(query.contains("今天")) values.put("date",today.toString());
        Matcher date=Pattern.compile("\\d{4}-\\d{2}-\\d{2}").matcher(query); if(date.find()) { try {values.put("date",LocalDate.parse(date.group()).toString());}catch(Exception ignored){} }
        return values;
    }
    private Map<String,Double> semantic(String query,List<Map<String,Object>> items) throws Exception {
        Map<String,Double> result=new HashMap<>();
        for(int offset=0;offset<items.size();offset+=1000) {
            List<Map<String,Object>> documents=items.subList(offset,Math.min(offset+1000,items.size())).stream().map(item->data("id",item.get("id"),"text",publicText(item))).toList();
            HttpRequest request=HttpRequest.newBuilder(URI.create(endpoint+"/score")).timeout(Duration.ofSeconds(8)).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(data("query",query,"documents",documents)))).build();
            HttpResponse<String> response=http.send(request,HttpResponse.BodyHandlers.ofString());
            if(response.statusCode()!=200) throw new IllegalStateException("model unavailable");
            Map<String,Object> body=json.readValue(response.body(),new TypeReference<>(){});
            if(!(body.get("scores") instanceof Map<?,?> scores)) throw new IllegalStateException("invalid model response");
            for(Map<String,Object> item:items.subList(offset,Math.min(offset+1000,items.size()))) {
                Object value=scores.get(item.get("id").toString());
                if(!(value instanceof Number number) || !Double.isFinite(number.doubleValue())) throw new IllegalStateException("invalid model score");
                result.put(item.get("id").toString(),number.doubleValue());
            }
        }
        return result;
    }
    public String publicText(Map<String,Object> item) { return str(item,"title")+" "+str(item,"category")+" "+str(item,"description")+" "+str(item,"location"); }
    public boolean healthy() {
        try { return http.send(HttpRequest.newBuilder(URI.create(endpoint+"/health")).timeout(Duration.ofSeconds(2)).GET().build(),HttpResponse.BodyHandlers.discarding()).statusCode()==200; }
        catch(Exception exception){return false;}
    }
    public Map<String,Object> search(Map<String,String> filters) {
        String query=filters.getOrDefault("q","").trim(); if(query.length()>200) throw fail(400,"查询内容最多 200 字");
        String from=filters.getOrDefault("from",""),to=filters.getOrDefault("to","");
        try { if(!from.isBlank()) LocalDate.parse(from); if(!to.isBlank()) LocalDate.parse(to); }catch(Exception exception){throw fail(400,"日期格式不正确");}
        if(!from.isBlank()&&!to.isBlank()&&from.compareTo(to)>0) throw fail(400,"开始日期不能晚于结束日期");
        List<Map<String,Object>> items=db.publicItems().stream().filter(item->{
            String status=filters.getOrDefault("status","");
            if(status.isBlank()&&!Set.of("OPEN","HANDOVER").contains(str(item,"status")))return false;
            for(String field:List.of("category","type","status")) {String value=filters.getOrDefault(field,""); if(!value.isBlank()&&!value.equals(str(item,field)))return false;}
            String location=filters.getOrDefault("location",""); if(!location.isBlank()&&!normalize(str(item,"location")).contains(normalize(location))) return false;
            String date=str(item,"event_date"); return (from.isBlank()||date.compareTo(from)>=0)&&(to.isBlank()||date.compareTo(to)<=0);
        }).toList();
        return rank(query,items,filters,null);
    }
    public Map<String,Object> matches(Map<String,Object> item) {
        List<Map<String,Object>> items=db.publicItems().stream().filter(candidate->!Objects.equals(candidate.get("type"),item.get("type"))&&id(candidate,"owner_id")!=id(item,"owner_id")&&"OPEN".equals(candidate.get("status"))).toList();
        return rank(str(item,"title")+" "+str(item,"description"),items,Map.of("pageSize","10"),item);
    }
    private Map<String,Object> rank(String query,List<Map<String,Object>> candidates,Map<String,String> filters,Map<String,Object> source) {
        Map<String,Object> hints=suggestions(query); if(source!=null) {hints.put("category",source.get("category"));hints.put("location",source.get("location"));hints.put("date",source.get("event_date"));}
        String mode=query.isBlank()?"recent":"keyword"; Map<String,Double> scores=Map.of();
        if(!query.isBlank()&&!candidates.isEmpty()) {try{scores=semantic(query,candidates); mode="hybrid";}catch(Exception exception){mode="keyword";}}
        List<Map<String,Object>> ranked=new ArrayList<>();
        for(Map<String,Object> original:candidates) {
            Map<String,Object> item=new LinkedHashMap<>(original); List<String> reasons=new ArrayList<>();
            if(!query.isBlank()) {
                String text=publicText(item);double similarity=scores.getOrDefault(item.get("id").toString(),0.0);
                if(!relevant(query,text,similarity))continue;
                double keyword=brandOnlyMatch(query,text)?1:lexical(query,text); double total=.25*keyword,weight=.25;
                if(keyword>0)reasons.add("关键词命中");
                if(mode.equals("hybrid")) {total+=.45*Math.max(0,Math.min(1,similarity));weight+=.45;item.put("semantic_score",similarity);if(keyword==0)reasons.add("语义相关");}
                if(hints.containsKey("category")&&!str(item,"category").isBlank()) { boolean same=Objects.equals(hints.get("category"),item.get("category"));total+=.15*(same?1:0);weight+=.15;if(same)reasons.add("物品同类"); }
                if(hints.containsKey("location")&&!str(item,"location").isBlank()) {double related=lexical(hints.get("location").toString(),str(item,"location"));total+=.10*related;weight+=.10;if(related==1)reasons.add("地点相关");}
                if(hints.containsKey("date")&&!str(item,"event_date").isBlank()) {
                    long days=ChronoUnit.DAYS.between(LocalDate.parse(hints.get("date").toString()),LocalDate.parse(str(item,"event_date")));
                    double temporal=1.0/(1+Math.abs(days)/7.0);
                    if(source!=null&&(("LOST".equals(source.get("type"))&&days<0)||("FOUND".equals(source.get("type"))&&days>0)))temporal*=.25;
                    total+=.05*temporal;weight+=.05;if(Math.abs(days)<=3)reasons.add("日期接近");
                }
                int conflicts=conflicts(query,publicText(item));double score=100*total/weight*Math.pow(.75,conflicts);
                if(score<MIN_SCORE)continue;
                item.put("score",Math.round(score*10)/10.0);
            }
            item.put("reasons",reasons);item.put("images",db.images(id(item,"id")));ranked.add(item);
        }
        if(!query.isBlank()) ranked.sort(Comparator.<Map<String,Object>>comparingDouble(item->((Number)item.get("score")).doubleValue()).reversed().thenComparing(item->str(item,"updated_at"),Comparator.reverseOrder()).thenComparingLong(item->-id(item,"id")));
        int page=number(filters,"page",1,1,100000),size=number(filters,"pageSize",10,1,50);int start=Math.min((page-1)*size,ranked.size());
        return data("items",ranked.subList(start,Math.min(start+size,ranked.size())),"total",ranked.size(),"page",page,"pageSize",size,"mode",mode,"suggestions",hints,"minScore",query.isBlank()?null:MIN_SCORE);
    }
    private int number(Map<String,String> values,String key,int fallback,int min,int max) {try{int value=Integer.parseInt(values.getOrDefault(key,Integer.toString(fallback)));if(value<min||value>max)throw new NumberFormatException();return value;}catch(NumberFormatException exception){throw fail(400,"分页参数不正确");}}
}
