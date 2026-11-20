package cn.campus.lostfound;

import static cn.campus.lostfound.Support.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.time.LocalDate;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.mock.web.*;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

public class SystemTest {
    static AnnotationConfigWebApplicationContext context;
    static Business business; static Db db; static Search search; static MockMvc mvc;
    static Map<String,Object> administrator;
    static final ObjectMapper JSON=new ObjectMapper();
    @BeforeAll static void setup() throws Exception {
        System.setProperty("app.data",Files.createTempDirectory(Path.of("target"),"test-data-").toString());
        System.setProperty("app.ai","http://127.0.0.1:1");
        context=new AnnotationConfigWebApplicationContext();context.setServletContext(new MockServletContext());context.register(AppConfig.class);context.refresh();
        business=context.getBean(Business.class);db=context.getBean(Db.class);search=context.getBean(Search.class);mvc=MockMvcBuilders.webAppContextSetup(context).build();administrator=db.userByName("admin");
    }
    @AfterAll static void shutdown(){if(context!=null)context.close();}
    Map<String,Object> newUser(){String name="user_"+UUID.randomUUID().toString().replace("-","").substring(0,12);Map<String,Object> user=business.register(data("username",name,"display_name","测试用户","password","TestPassword123"));return db.user(id(user,"id"));}
    Map<String,Object> itemInput(){return data("type","FOUND","title","图书馆黑色折叠雨伞","category","雨伞","description","黑色折叠伞，伞柄有一条挂绳","location","图书馆","event_date",LocalDate.now().minusDays(1).toString(),"contact","秘密联系方式","hidden_features","秘密核验特征","images",List.of());}
    Map<String,Object> openItem(Map<String,Object> owner){Map<String,Object> item=business.createItem(owner,itemInput());business.review(administrator,id(item,"id"),true,"");return db.item(id(item,"id"));}
    Map<String,Object> apply(Map<String,Object> user,Map<String,Object> item){return business.apply(user,id(item,"id"),data("proof","遗失在图书馆，伞柄挂绳里有我的缩写"));}
    MockHttpSession session(Map<String,Object> user){MockHttpSession result=new MockHttpSession();result.setAttribute("uid",id(user,"id"));result.setAttribute("csrf","test-token");return result;}
    @Test void passwordsAreSaltedAndVerified(){String first=hash("password123"),second=hash("password123");assertNotEquals(first,second);assertTrue(verify("password123",first));assertFalse(verify("wrong",first));}
    @Test void ownershipIsEnforced(){Map<String,Object> owner=newUser(),other=newUser(),item=openItem(owner);assertEquals(403,assertThrows(AppException.class,()->business.editItem(other,id(item,"id"),itemInput())).status);assertEquals(403,assertThrows(AppException.class,()->business.deleteItem(other,id(item,"id"))).status);}
    @Test void hiddenFieldsNeverLeakToPublicOrModel(){Map<String,Object> item=openItem(newUser());Map<String,Object> publicView=business.detail(id(item,"id"),null);assertFalse(publicView.containsKey("contact"));assertFalse(publicView.containsKey("hidden_features"));assertFalse(search.publicText(item).contains("秘密"));assertFalse(db.publicItems().stream().anyMatch(value->value.containsKey("contact")||value.containsKey("hidden_features")));}
    @Test void pendingInformationIsPrivate(){Map<String,Object> owner=newUser(),item=business.createItem(owner,itemInput());assertEquals(404,assertThrows(AppException.class,()->business.detail(id(item,"id"),null)).status);assertNotNull(business.detail(id(item,"id"),owner));}
    @Test void multipleApplicationsOneHandoverAndOneRecipient(){Map<String,Object> owner=newUser(),first=newUser(),second=newUser(),item=openItem(owner);Map<String,Object> claimOne=apply(first,item),claimTwo=apply(second,item);assertEquals(2,db.pendingCount(id(item,"id")));business.claimAction(administrator,id(claimOne,"id"),"approve","");assertEquals("HANDOVER",db.item(id(item,"id")).get("status"));assertThrows(AppException.class,()->business.claimAction(administrator,id(claimTwo,"id"),"approve",""));assertFalse(business.detail(id(item,"id"),second).containsKey("contact"));assertTrue(business.detail(id(item,"id"),first).containsKey("contact"));business.claimAction(administrator,id(claimOne,"id"),"complete","");assertEquals("CLAIMED",db.item(id(item,"id")).get("status"));assertEquals("COMPLETED",db.claim(id(claimOne,"id")).get("status"));assertEquals("CANCELLED",db.claim(id(claimTwo,"id")).get("status"));assertThrows(AppException.class,()->business.claimAction(administrator,id(claimOne,"id"),"complete",""));}
    @Test void concurrentApprovalsHaveOnlyOneWinner() throws Exception {
        Map<String,Object> item=openItem(newUser()),first=apply(newUser(),item),second=apply(newUser(),item);CountDownLatch gate=new CountDownLatch(1);ExecutorService executor=Executors.newFixedThreadPool(2);
        try{List<Future<Boolean>> attempts=new ArrayList<>();for(Map<String,Object> claim:List.of(first,second))attempts.add(executor.submit(()->{gate.await();try{business.claimAction(administrator,id(claim,"id"),"approve","");return true;}catch(RuntimeException exception){return false;}}));gate.countDown();int successes=0;for(Future<Boolean> attempt:attempts)if(attempt.get(15,TimeUnit.SECONDS))successes++;assertEquals(1,successes);assertEquals(1,db.itemActiveClaims(id(item,"id")).stream().filter(value->"APPROVED".equals(value.get("status"))).count());}finally{executor.shutdownNow();}
    }
    @Test void duplicateActiveApplicationsAndSelfClaimsAreRejected(){Map<String,Object> owner=newUser(),item=openItem(owner),applicant=newUser();assertThrows(AppException.class,()->apply(owner,item));apply(applicant,item);assertThrows(org.springframework.dao.DataIntegrityViolationException.class,()->apply(applicant,item));}
    @Test void editingRequiresReviewAndLocksAfterClaim(){Map<String,Object> owner=newUser(),item=openItem(owner);business.editItem(owner,id(item,"id"),itemInput());assertEquals("PENDING",db.item(id(item,"id")).get("status"));business.review(administrator,id(item,"id"),true,"");apply(newUser(),item);assertThrows(AppException.class,()->business.editItem(owner,id(item,"id"),itemInput()));}
    @Test void cancelledHandoverReopensItem(){Map<String,Object> item=openItem(newUser()),claim=apply(newUser(),item);business.claimAction(administrator,id(claim,"id"),"approve","");business.claimAction(administrator,id(claim,"id"),"cancel","无法确认所有权");assertEquals("OPEN",db.item(id(item,"id")).get("status"));assertEquals("CANCELLED",db.claim(id(claim,"id")).get("status"));}
    @Test void closingCancelsAllActiveClaims(){Map<String,Object> item=openItem(newUser()),claim=apply(newUser(),item);business.close(administrator,id(item,"id"),false);assertEquals("CANCELLED",db.claim(id(claim,"id")).get("status"));assertEquals("CLOSED",db.item(id(item,"id")).get("status"));}
    @Test void accountDeletionRequiresFinishedBusiness(){Map<String,Object> owner=newUser(),item=openItem(owner);assertThrows(AppException.class,()->business.deleteAccount(owner,"TestPassword123"));business.close(owner,id(item,"id"),false);business.deleteAccount(owner,"TestPassword123");assertEquals("DELETED",db.user(id(owner,"id")).get("status"));assertEquals("",db.user(id(owner,"id")).get("password_hash"));assertTrue(db.ownItems(id(owner,"id")).isEmpty());}
    @Test void banningInvalidatesExistingSession() throws Exception {Map<String,Object> user=newUser();MockHttpSession current=session(user);business.accountAction(administrator,id(user,"id"),"ban","违规发布");mvc.perform(get("/api/mine/items").session(current)).andExpect(status().isForbidden());business.accountAction(administrator,id(user,"id"),"unlock","核验完成");mvc.perform(get("/api/mine/items").session(current)).andExpect(status().isOk());}
    @Test void csrfAndAdminAccessAreEnforced() throws Exception {MockHttpSession current=session(newUser());mvc.perform(post("/api/items").session(current).contentType("application/json").content(JSON.writeValueAsString(itemInput()))).andExpect(status().isForbidden());mvc.perform(get("/api/admin/users").session(current)).andExpect(status().isForbidden());mvc.perform(post("/api/items").session(current).header("X-CSRF-Token","test-token").contentType("application/json").content(JSON.writeValueAsString(itemInput()))).andExpect(status().isOk());}
    @Test void synonymNormalizationConflictAndFallback(){assertEquals(1,Search.lexical("学生卡","校园卡"));assertEquals(2,Search.conflicts("黑色华为手机","白色苹果手机"));assertEquals(0,Search.conflicts("黑色华为手机","一部手机"));Map<String,Object> item=openItem(newUser());Map<String,Object> results=search.search(Map.of("q","黑色折叠伞","type","FOUND"));assertEquals("keyword",results.get("mode"));assertTrue(((Number)results.get("total")).intValue()>0);Map<String,Object> none=search.search(Map.of("q","黑色折叠伞","category","证件卡片"));assertEquals(0,none.get("total"));assertNotNull(item);}
    @Test void proofsAndFakeImagesAreProtected() throws Exception {Map<String,Object> owner=newUser(),other=newUser();Map<String,Object> attachment=data("owner_id",owner.get("id"),"stored_name","private.png","mime","image/png","kind","PROOF","created_at",now());db.insertAttachment(attachment);mvc.perform(get("/media/"+attachment.get("id")).session(session(other))).andExpect(status().isForbidden());MockMultipartFile fake=new MockMultipartFile("file","image.png","image/png","<script>bad</script>".getBytes());mvc.perform(multipart("/api/uploads").file(fake).session(session(owner)).header("X-CSRF-Token","test-token")).andExpect(status().isBadRequest());}
    @Test void invalidInputAndDateFiltersAreRejected(){Map<String,Object> input=itemInput();input.put("event_date",LocalDate.now().plusDays(2).toString());assertThrows(AppException.class,()->business.createItem(newUser(),input));assertThrows(AppException.class,()->search.search(Map.of("from","2026-11-20","to","2026-11-01")));}
    @Test void expiredSessionIsDistinctFromCsrfFailure() throws Exception {
        mvc.perform(post("/api/items").header("X-CSRF-Token","expired-token").contentType("application/json").content(JSON.writeValueAsString(itemInput())))
            .andExpect(status().isUnauthorized()).andExpect(result->assertEquals("登录态过期，请重新登录后再操作",JSON.readTree(result.getResponse().getContentAsByteArray()).get("error").asText()));
        mvc.perform(post("/api/items").session(session(newUser())).header("X-CSRF-Token","wrong-token").contentType("application/json").content(JSON.writeValueAsString(itemInput())))
            .andExpect(status().isForbidden()).andExpect(result->assertEquals("页面验证已失效，请刷新后重试",JSON.readTree(result.getResponse().getContentAsByteArray()).get("error").asText()));
        mvc.perform(get("/api/mine/items")).andExpect(status().isUnauthorized());
    }
    @Test void refreshedSessionCanLoginAndRotateCsrf() throws Exception {
        Map<String,Object> user=newUser();
        var refreshed=mvc.perform(get("/api/session")).andExpect(status().isOk()).andReturn();
        MockHttpSession current=(MockHttpSession)refreshed.getRequest().getSession();String csrf=(String)current.getAttribute("csrf");
        var response=mvc.perform(post("/api/login").session(current).header("X-CSRF-Token",csrf).contentType("application/json").content(JSON.writeValueAsString(data("username",user.get("username"),"password","TestPassword123"))))
            .andExpect(status().isOk()).andReturn();
        Map<String,Object> result=JSON.readValue(response.getResponse().getContentAsString(),Map.class);
        assertNotEquals(csrf,result.get("csrf"));assertEquals(id(user,"id"),((Number)current.getAttribute("uid")).longValue());
        mvc.perform(get("/api/mine/items").session(current)).andExpect(status().isOk());
    }
    Map<String,Object> searchableItem(String title,String description,String category) {
        Map<String,Object> input=itemInput();input.put("title",title);input.put("description",description);input.put("category",category);
        Map<String,Object> item=business.createItem(newUser(),input);business.review(administrator,id(item,"id"),true,"");return db.item(id(item,"id"));
    }
    @Test void keywordSearchFiltersBrandsObjectsAndEmptyQueriesStillBrowse() {
        var apple=searchableItem("苹果 iPhone 15 手机","白色手机，透明保护壳","数码电子");
        var huawei=searchableItem("华为 Mate 60 手机","黑色手机，透明保护壳","数码电子");
        var umbrella=openItem(newUser());
        Map<String,Object> result=search.search(Map.of("q","苹果","pageSize","1"));
        assertEquals(1,result.get("total"));assertEquals(30.0,result.get("minScore"));
        assertEquals(id(apple,"id"),id(((List<Map<String,Object>>)result.get("items")).getFirst(),"id"));
        assertTrue(((List<?>)search.search(Map.of("q","苹果","page","2","pageSize","1")).get("items")).isEmpty());
        var recent=search.search(Map.of());assertTrue((int)recent.get("total")>=3);assertNull(recent.get("minScore"));
        assertEquals(0,search.search(Map.of("q","完全不存在的紫水晶吊坠")).get("total"));
        assertFalse(Search.relevant("黑色雨伞","图书馆黑色手机",.99));
        assertFalse(Search.relevant("苹果","图书馆黑色雨伞",.99));
        assertFalse(Search.relevant("iphone15","苹果iphone150手机",.99));
        assertFalse(Search.relevant("白色苹果手机","黑色苹果手机",.99));
        assertTrue(Search.relevant("苹果","白色 iPhone 15 手机",.4));
        assertTrue(Search.relevant("学生卡","蓝色校园卡",0));
        assertFalse(Search.relevant("开门的小东西","铜制钥匙",.44));
        assertTrue(Search.relevant("开门的小东西","铜制钥匙",.45));
    }
    @Test void hybridSearchFiltersBeforeCountingAndPaging() throws Exception {
        var low=searchableItem("远航纪念徽章甲","纪念活动留下的一枚徽章","其他");
        var high=searchableItem("远航纪念徽章乙","纪念活动留下的一枚徽章","其他");
        var unrelated=searchableItem("蓝鲸图案雨伞","雨伞外观带有鲸鱼图案","雨伞");
        Map<String,Double> scores=Map.of(low.get("id").toString(),.28145,high.get("id").toString(),.2815,unrelated.get("id").toString(),.01);
        HttpServer model=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        model.createContext("/score",exchange->{
            Map<String,Object> request=JSON.readValue(exchange.getRequestBody(),Map.class);Map<String,Double> values=new HashMap<>();
            for(var item:(List<Map<String,Object>>)request.get("documents"))values.put(item.get("id").toString(),scores.getOrDefault(item.get("id").toString(),0.0));
            byte[] body=JSON.writeValueAsBytes(data("scores",values));exchange.sendResponseHeaders(200,body.length);try(var output=exchange.getResponseBody()){output.write(body);}
        });model.start();String previous=System.getProperty("app.ai");
        try {
            System.setProperty("app.ai","http://127.0.0.1:"+model.getAddress().getPort());Search hybrid=new Search(db);
            var result=hybrid.search(Map.of("q","远航蓝鲸","pageSize","1"));
            assertEquals("hybrid",result.get("mode"));assertEquals(1,result.get("total"));
            var items=(List<Map<String,Object>>)result.get("items");assertEquals(id(high,"id"),id(items.getFirst(),"id"));assertEquals(30.0,items.getFirst().get("score"));
            assertTrue(((List<?>)hybrid.search(Map.of("q","远航蓝鲸","pageSize","1","page","2")).get("items")).isEmpty());
        }finally{model.stop(0);System.setProperty("app.ai",previous);}
    }
}
