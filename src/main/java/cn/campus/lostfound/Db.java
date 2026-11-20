package cn.campus.lostfound;

import org.apache.ibatis.annotations.*;
import java.util.*;

@Mapper
public interface Db {
    @Select("SELECT * FROM users WHERE id=#{id}") Map<String,Object> user(long id);
    @Select("SELECT * FROM users WHERE username=#{name}") Map<String,Object> userByName(String name);
    @Select("SELECT id,username,display_name,role,status,ban_reason,created_at FROM users ORDER BY id DESC") List<Map<String,Object>> users();
    @Insert("INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES(#{username},#{display_name},#{password_hash},#{role},#{created_at})")
    @Options(useGeneratedKeys=true,keyProperty="id") int insertUser(Map<String,Object> values);
    @Update("UPDATE users SET status=#{status},ban_reason=#{reason} WHERE id=#{id} AND role='USER' AND status != 'DELETED'") int userStatus(@Param("id") long id,@Param("status") String status,@Param("reason") String reason);
    @Update("UPDATE users SET status='DELETED',username='deleted:'||id,display_name='已注销用户',password_hash='',ban_reason='' WHERE id=#{id} AND role='USER' AND status!='DELETED'") int anonymize(long id);
    @Select("SELECT * FROM items WHERE id=#{id} AND deleted=0") Map<String,Object> item(long id);
    @Select("SELECT i.*,u.display_name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.deleted=0 ORDER BY i.updated_at DESC,i.id DESC") List<Map<String,Object>> allItems();
    @Select("SELECT i.id,i.owner_id,i.type,i.title,i.category,i.description,i.location,i.event_date,i.status,i.created_at,i.updated_at,u.display_name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.deleted=0 AND u.status='ACTIVE' AND i.status IN ('OPEN','HANDOVER','CLAIMED','RESOLVED','CLOSED') ORDER BY i.updated_at DESC,i.id DESC") List<Map<String,Object>> publicItems();
    @Select("SELECT * FROM items WHERE owner_id=#{id} AND deleted=0 ORDER BY id DESC") List<Map<String,Object>> ownItems(long id);
    @Insert("INSERT INTO items(owner_id,type,title,category,description,location,event_date,contact,hidden_features,status,created_at,updated_at) VALUES(#{owner_id},#{type},#{title},#{category},#{description},#{location},#{event_date},#{contact},#{hidden_features},#{status},#{created_at},#{updated_at})")
    @Options(useGeneratedKeys=true,keyProperty="id") int insertItem(Map<String,Object> values);
    @Update("UPDATE items SET type=#{type},title=#{title},category=#{category},description=#{description},location=#{location},event_date=#{event_date},contact=#{contact},hidden_features=#{hidden_features},status='PENDING',review_note='',updated_at=#{updated_at} WHERE id=#{id} AND deleted=0 AND status NOT IN ('HANDOVER','CLAIMED','RESOLVED','CLOSED') AND NOT EXISTS(SELECT 1 FROM claims WHERE item_id=items.id)") int editItem(Map<String,Object> values);
    @Update("UPDATE items SET status=#{next},review_note=#{reason},updated_at=#{time} WHERE id=#{id} AND status=#{expected} AND deleted=0") int itemState(@Param("id") long id,@Param("expected") String expected,@Param("next") String next,@Param("reason") String reason,@Param("time") String time);
    @Update("UPDATE items SET deleted=1,updated_at=#{time} WHERE id=#{id} AND deleted=0") int deleteItem(@Param("id") long id,@Param("time") String time);
    @Update("UPDATE items SET deleted=1 WHERE owner_id=#{id}") int hideOwnItems(long id);
    @Select("SELECT COUNT(*) FROM items WHERE owner_id=#{id} AND deleted=0 AND status IN ('PENDING','OPEN','HANDOVER')") int activeItems(long id);
    @Select("SELECT COUNT(*) FROM claims WHERE applicant_id=#{id} AND status IN ('PENDING','APPROVED')") int activeClaims(long id);
    @Select("SELECT COUNT(*) FROM claims WHERE item_id=#{id}") int claimCount(long id);
    @Select("SELECT COUNT(*) FROM claims WHERE item_id=#{id} AND status IN ('PENDING','APPROVED')") int pendingCount(long id);
    @Insert("INSERT INTO claims(item_id,applicant_id,proof,proof_attachment_id,status,created_at,updated_at) VALUES(#{item_id},#{applicant_id},#{proof},#{proof_attachment_id},'PENDING',#{created_at},#{updated_at})")
    @Options(useGeneratedKeys=true,keyProperty="id") int insertClaim(Map<String,Object> values);
    @Select("SELECT c.*,i.title,i.owner_id,u.display_name AS applicant_name FROM claims c JOIN items i ON i.id=c.item_id JOIN users u ON u.id=c.applicant_id WHERE c.id=#{id}") Map<String,Object> claim(long id);
    @Select("SELECT c.*,i.title,i.status AS item_status,u.display_name AS applicant_name FROM claims c JOIN items i ON i.id=c.item_id JOIN users u ON u.id=c.applicant_id ORDER BY c.id DESC") List<Map<String,Object>> claims();
    @Select("SELECT * FROM claims WHERE item_id=#{id} AND status IN ('PENDING','APPROVED')") List<Map<String,Object>> itemActiveClaims(long id);
    @Select("SELECT COUNT(*) FROM claims WHERE item_id=#{item} AND applicant_id=#{user} AND status IN ('APPROVED','COMPLETED')") int contactAllowed(@Param("item") long item,@Param("user") long user);
    @Update("UPDATE claims SET status=#{next},review_note=#{reason},updated_at=#{time} WHERE id=#{id} AND status=#{expected}") int claimState(@Param("id") long id,@Param("expected") String expected,@Param("next") String next,@Param("reason") String reason,@Param("time") String time);
    @Insert("INSERT INTO notifications(user_id,message,created_at) VALUES(#{user},#{message},#{time})") int notify(@Param("user") long user,@Param("message") String message,@Param("time") String time);
    @Select("SELECT * FROM notifications WHERE user_id=#{id} ORDER BY id DESC LIMIT 200") List<Map<String,Object>> notifications(long id);
    @Update("UPDATE notifications SET is_read=1 WHERE user_id=#{id}") int readNotifications(long id);
    @Insert("INSERT INTO audit_logs(actor_id,action,target_type,target_id,reason,created_at) VALUES(#{actor},#{action},#{type},#{target},#{reason},#{time})") int audit(@Param("actor") long actor,@Param("action") String action,@Param("type") String type,@Param("target") long target,@Param("reason") String reason,@Param("time") String time);
    @Select("SELECT a.*,u.display_name AS actor_name FROM audit_logs a JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 300") List<Map<String,Object>> logs();
    @Insert("INSERT INTO attachments(owner_id,stored_name,mime,kind,created_at) VALUES(#{owner_id},#{stored_name},#{mime},#{kind},#{created_at})")
    @Options(useGeneratedKeys=true,keyProperty="id") int insertAttachment(Map<String,Object> values);
    @Select("SELECT * FROM attachments WHERE id=#{id}") Map<String,Object> attachment(long id);
    @Insert("INSERT INTO item_images(item_id,attachment_id) VALUES(#{item},#{attachment})") int linkImage(@Param("item") long item,@Param("attachment") long attachment);
    @Delete("DELETE FROM item_images WHERE item_id=#{id}") int unlinkImages(long id);
    @Select("SELECT attachment_id FROM item_images WHERE item_id=#{id} ORDER BY attachment_id") List<Long> images(long id);
    @Select("SELECT item_id FROM item_images WHERE attachment_id=#{id}") Long imageItem(long id);
}
